#!/usr/bin/env python3
"""Autonomous TPC-DS test campaign for the SQL agent PoC.

Runs fully unattended on the server:
1. waits for the API container to become healthy;
2. runs the learning stages (survey -> explore -> optimize -> evolve);
3. asks each block concurrently (adaptive service limiters keep pressure in
   the 1-8 range) while preserving corpus order;
4. queues every failure immediately and retries that exact question after a
   successful immutable promotion;
5. optionally scores answered questions with a judge model (CAMPAIGN_JUDGE_*):
   verdicts land in Results.md only, but a rejected answer triggers the
   learning stages and a rerun of the whole block (up to CAMPAIGN_JUDGE_MAX_LOOPS);
6. stops asking new questions after the global time budget (default 6 h);
7. writes a completion/useful-outcomes report without an accuracy oracle and
   commits + pushes it to GitHub.

Only stdlib is used, so the system python3 on the server is enough.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import judge  # imported as a package (tests)
except ImportError:  # run directly as scripts/test_campaign.py on the server
    import judge

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = Path(os.getenv("CAMPAIGN_QUESTIONS", REPO_ROOT / "evals" / "test_campaign.json"))
RESULTS_PATH = Path(os.getenv("CAMPAIGN_RESULTS", REPO_ROOT / "Results.md"))
TIME_BUDGET_HOURS = float(os.getenv("CAMPAIGN_TIME_BUDGET_HOURS", "6"))
ASK_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_ASK_TIMEOUT_SEC", "1800"))
JOB_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_JOB_TIMEOUT_SEC", "3600"))
CAMPAIGN_CONCURRENCY = max(1, min(12, int(os.getenv("CAMPAIGN_CONCURRENCY", "12"))))
LEARNING_RETRY_WAIT_SEC = float(os.getenv("CAMPAIGN_LEARNING_RETRY_WAIT_SEC", "1800"))
GIT_PUSH = os.getenv("CAMPAIGN_GIT_PUSH", "1").strip() not in {"0", "false", "no"}
# Comma-separated stage names to skip on resume (e.g. "survey,explore,optimize,evolve,verify").
SKIP_STAGES = {name.strip() for name in os.getenv("CAMPAIGN_SKIP_STAGES", "").split(",") if name.strip()}
# Judge mode: "report" only annotates Results.md; "enforce" marks answers the
# judge rejects as judge_failed. Either way nothing is fed back to the agent.
JUDGE_MODE = os.getenv("CAMPAIGN_JUDGE_MODE", "report").strip().lower()
# How many improvement-loop + block-rerun cycles a judge rejection may trigger
# per block (0 = judge never reruns blocks).
JUDGE_MAX_LOOPS = max(0, int(os.getenv("CAMPAIGN_JUDGE_MAX_LOOPS", "1")))


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def http(method: str, path: str, payload: dict | None = None, timeout: float = 60.0) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        API_BASE + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            structured = json.loads(raw)
        except ValueError:
            structured = None
        if isinstance(structured, dict) and structured.get("request_id") and structured.get("error"):
            return structured
        detail = raw[:500]
        return {"__http_error__": exc.code, "detail": detail}
    except Exception as exc:  # timeouts, connection resets — the campaign must go on
        return {"__http_error__": None, "detail": str(exc)[:500]}


def wait_for_api() -> bool:
    # No timeout: a fresh workspace makes the entrypoint survey the whole database
    # before uvicorn starts, and that can take arbitrarily long on big scales.
    while True:
        health = http("GET", "/api/health", timeout=15)
        if health.get("ok"):
            return True
        time.sleep(30)


def run_job(name: str, path: str) -> dict:
    started = http("POST", path, timeout=60)
    job_id = started.get("job_id")
    if not job_id:
        log(f"job {name}: failed to start: {started}")
        return {"name": name, "status": "start_failed", "detail": started}
    log(f"job {name} started ({job_id})")
    deadline = time.monotonic() + JOB_TIMEOUT_SEC
    while time.monotonic() < deadline:
        time.sleep(20)
        job = http("GET", f"/api/jobs/{job_id}", timeout=30)
        status = job.get("status")
        if status and status != "running":
            log(f"job {name} -> {status}")
            return job
    return {"name": name, "status": "timeout"}


def learning_loop(rounds_note: str) -> dict:
    """All evolution/exploration stages, in dependency order."""
    outcomes = {}
    for stage in ("explore", "optimize", "evolve", "promote", "verify"):
        if stage in SKIP_STAGES:
            outcomes[stage] = {"status": "skipped_env"}
        else:
            outcomes[stage] = run_job(stage, f"/api/{stage}")
    log(f"learning loop ({rounds_note}) done: "
        + ", ".join(f"{k}={v.get('status')}" for k, v in outcomes.items()))
    return outcomes


def _json_safe(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


def ask(question: str) -> dict:
    started = time.perf_counter()
    response = http("POST", "/api/ask", {"question": question}, timeout=ASK_TIMEOUT_SEC)
    elapsed = time.perf_counter() - started
    if "__http_error__" in response:
        code = response["__http_error__"]
        detail = response.get("detail", "")
        # 422 carries the agent's own error payload; anything else is infra.
        return {
            "question": question,
            "status": "pipeline_failed",
            "error": f"HTTP {code}: {detail}" if code else f"transport: {detail}",
            "error_type": "llm_transport_error" if code is None else "internal_error",
            "error_stage": "transport",
            "elapsed_sec": round(elapsed, 1),
        }
    error = response.get("error") or {}
    if isinstance(error, str):
        error = {"type": "internal_error", "message": error, "stage": "unknown", "retryable": False}
    clarification = bool(response.get("clarification"))
    status = str(response.get("status") or ("clarified" if clarification else ("pipeline_failed" if error else "answered")))
    spans = (response.get("telemetry") or {}).get("spans") or []
    prompt_tokens = sum(span.get("attributes", {}).get("prompt_tokens") or 0 for span in spans)
    completion_tokens = sum(span.get("attributes", {}).get("completion_tokens") or 0 for span in spans)
    return {
        "question": question,
        "request_id": response.get("request_id"),
        "status": status,
        "error": error.get("message", ""),
        "error_type": error.get("type"),
        "error_stage": error.get("stage"),
        "retryable": error.get("retryable"),
        "learning_job_id": error.get("learning_job_id"),
        "elapsed_sec": round(elapsed, 1),
        "agent_elapsed_ms": (response.get("result") or {}).get("elapsed_ms"),
        "rows": len((response.get("result") or {}).get("rows") or []),
        "react_attempts": (response.get("react") or {}).get("attempts", 0),
        "route": response.get("route", ""),
        "template": response.get("template") or "",
        "sql": (response.get("sql") or "")[:600],
        "sql_full": (response.get("sql") or "")[:4000],
        "row_sample": _json_safe((response.get("result") or {}).get("rows") or [])[:20],
        "clarification": response.get("clarification") or "",
        "tool_calls": len(spans),
        "prompt_tokens": prompt_tokens if spans else None,
        "completion_tokens": completion_tokens if spans else None,
    }


def wait_for_promotion(job_id: str) -> bool:
    deadline = time.monotonic() + LEARNING_RETRY_WAIT_SEC
    while time.monotonic() < deadline:
        job = http("GET", f"/api/learning/{job_id}", timeout=30)
        status = job.get("status")
        if status in {"completed", "rejected", "failed", "incident"}:
            return status == "completed" and (job.get("result") or {}).get("status") == "promoted"
        time.sleep(2)
    return False


def collect_background_results(blocks_report: list[dict]) -> list[dict]:
    """Final statuses of the background learner jobs queued by failures."""
    outcomes = []
    for block in blocks_report:
        for item in block["questions"]:
            job_id = item.get("learning_job_id")
            if not job_id:
                continue
            job = http("GET", f"/api/learning/{job_id}", timeout=15)
            outcomes.append({
                "job_id": job_id,
                "question": item["question"],
                "status": job.get("status") or "unknown",
                "result": (job.get("result") or {}).get("status") or "",
            })
    return outcomes


def judge_block(results: list[dict], agent_info: dict) -> int:
    """Judge not-yet-judged answered items of a block; return the reject count.

    Verdicts are never sent back to the agent — improvement runs through the
    agent's own learning stages, not through judge feedback."""
    base_url = judge.JUDGE_BASE_URL or (agent_info.get("base_url") or "")
    incorrect = 0
    for item in results:
        if item.get("status") != "answered" or "judge" in item:
            continue
        verdict = judge.judge_answer(
            item["question"],
            item.get("sql_full", ""),
            item.get("rows") or 0,
            item.get("row_sample") or [],
            base_url,
        )
        item["judge"] = verdict
        if verdict["verdict"] == "incorrect":
            incorrect += 1
            if JUDGE_MODE == "enforce":
                item["status"] = "judge_failed"
                item["error"] = f"judge rejected: {verdict['reason']}"
                item["error_type"] = item.get("error_type") or "judge_rejected"
                item["error_stage"] = item.get("error_stage") or "judge"
        log(f"judge: {verdict['verdict']} — {item['question'][:60]}")
    return incorrect


def recount(blocks_report: list[dict], totals: dict) -> None:
    """Recompute per-block and total counts after judge verdicts flipped statuses."""
    keys = ("answered", "clarified", "pipeline_failed", "skipped", "judge_failed", "answered_empty")
    for key in keys:
        totals[key] = 0
    for block in blocks_report:
        counts = {key: 0 for key in keys}
        for item in block["questions"]:
            status = item["status"] if item["status"] in counts else "pipeline_failed"
            counts[status] += 1
            if item["status"] == "answered" and not item.get("rows"):
                counts["answered_empty"] += 1
        block.update(counts)
        for key in keys:
            totals[key] += counts[key]


def run_block(questions: list[str], eligible: list[bool], budget_deadline: float) -> tuple[list[dict], int]:
    """Ask a block's questions, then retry failures the background learner rescued."""
    runnable = [question for question, allowed in zip(questions, eligible) if allowed]
    completed = iter(run_questions_ordered(runnable))
    results = [
        next(completed) if allowed else {"question": question, "status": "skipped", "error": "time budget exhausted"}
        for question, allowed in zip(questions, eligible)
    ]

    rescued = 0
    for index, item in enumerate(list(results)):
        job_id = item.get("learning_job_id")
        if item.get("status") != "pipeline_failed" or not job_id:
            continue
        if time.monotonic() > budget_deadline:
            break
        if wait_for_promotion(job_id):
            retry = ask(item["question"])
            retry["retried"] = True
            if retry["status"] in {"answered", "clarified"}:
                rescued += 1
            results[index] = retry
    return results, rescued


def run_questions_ordered(
    questions: list[str],
    ask_fn=ask,
    concurrency: int = CAMPAIGN_CONCURRENCY,
) -> list[dict]:
    """Run independent questions concurrently while retaining corpus order."""

    with ThreadPoolExecutor(max_workers=max(1, min(12, concurrency)), thread_name_prefix="campaign-question") as pool:
        futures = [pool.submit(ask_fn, question) for question in questions]
        return [future.result() for future in futures]


def render_results(report: dict) -> str:
    lines = [
        "# SQL Agent TPC-DS Test Campaign — Results",
        "",
        f"- Started: {report['started_at']}",
        f"- Finished: {report['finished_at']}",
        f"- Total wall time: {report['total_elapsed_min']} min (budget {report['time_budget_hours']} h)",
        f"- Agent: `{report['agent']}`",
        "",
        "## Summary",
        "",
        "| Block | Questions | Answered | Clarified | Pipeline failed | Empty answers | Judge failed | Rescued | Block time |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for block in report["blocks"]:
        lines.append(
            f"| {block['title']} | {len(block['questions'])} | {block['answered']} | "
            f"{block['clarified']} | {block['pipeline_failed']} | {block.get('answered_empty', 0)} | "
            f"{block.get('judge_failed', 0)} | {block['rescued_retries']} | {block['elapsed_min']} min |"
        )
    lines += [
        "",
        f"**Total: {report['totals']['answered']} answered / {report['totals']['clarified']} clarified / "
        f"{report['totals']['pipeline_failed']} pipeline failed / {report['totals'].get('judge_failed', 0)} judge failed / "
        f"{report['totals']['skipped']} skipped out of {report['totals']['questions']}**",
        "",
        f"Useful outcomes: {report['totals']['answered'] + report['totals']['clarified']}; rescued retries: {report['totals']['rescued_retries']}; "
        f"answered with 0 rows: {report['totals'].get('answered_empty', 0)}; "
        f"tool calls: {report['totals']['tool_calls']}; prompt/completion tokens: {report['totals']['prompt_tokens']}/{report['totals']['completion_tokens']}.",
        "",
        "## Learning stages",
        "",
        "```",
        json.dumps(report["stages"], ensure_ascii=False, indent=2, default=str)[:4000],
        "```",
        "",
    ]
    if report.get("judge"):
        judge_info = report["judge"]
        counts = judge_info["counts"]
        lines += [
            f"## Judge ({judge_info['model']}, mode={judge_info['mode']})",
            "",
            f"correct: {counts['correct']} / partially_correct: {counts['partially_correct']} / "
            f"incorrect: {counts['incorrect']} / inconclusive: {counts['inconclusive']}; "
            f"improvement reruns triggered: {judge_info.get('reruns', 0)}",
            "",
        ]
    if report.get("background"):
        lines += [
            "## Background learning (post-failure repair)",
            "",
            "| Job | Question | Final status |",
            "|---|---|---|",
        ]
        for entry in report["background"]:
            final = entry["status"] + (f" ({entry['result']})" if entry.get("result") else "")
            lines.append(f"| {entry['job_id'][:8]} | {entry['question']} | {final} |")
        lines.append("")
    lines += [
        "## Per-question detail",
        "",
    ]
    judge_on = bool(report.get("judge"))
    for block in report["blocks"]:
        lines.append(f"### {block['title']} (`{block['name']}`)")
        lines.append("")
        if judge_on:
            lines.append("| # | Question | Status | Time, s | Rows | Tools | Judge | Error type/stage |")
            lines.append("|---|---|---|---|---|---|---|---|")
        else:
            lines.append("| # | Question | Status | Time, s | Rows | Tools | Error type/stage |")
            lines.append("|---|---|---|---|---|---|---|")
        for index, item in enumerate(block["questions"], 1):
            error = (item.get("error") or "").replace("|", "\\|")[:120]
            status = item["status"]
            if status == "answered" and not item.get("rows"):
                status = "answered (empty)"
            row = (
                f"| {index} | {item['question']} | {status} | {item.get('elapsed_sec', '-')} | "
                f"{item.get('rows', '-')} | {item.get('tool_calls', '-')} |"
            )
            if judge_on:
                verdict = (item.get("judge") or {}).get("verdict", "-")
                row += f" {verdict} |"
            lines.append(f"{row} {item.get('error_type') or ''}/{item.get('error_stage') or ''}: {error} |")
        lines.append("")
    lines += [
        "## Environment",
        "",
        "```",
        json.dumps(report["environment"], ensure_ascii=False, indent=2, default=str),
        "```",
        "",
    ]
    return "\n".join(lines)


def git_publish() -> str:
    def run(command: list[str]) -> tuple[int, str]:
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        return completed.returncode, f"$ {' '.join(command)}\n{completed.stdout}{completed.stderr}".strip()

    output = []
    for command in (
        ["git", "add", str(RESULTS_PATH.name)],
        ["git", "-c", "user.name=sqlagent-campaign", "-c", "user.email=sqlagent-campaign@localhost",
         "commit", "-m", f"test campaign results {datetime.now(timezone.utc).date().isoformat()}"],
    ):
        code, text = run(command)
        output.append(text)
    if not GIT_PUSH:
        return "\n".join(output)

    # Publish on the campaign's own branch: the exact code state plus Results.md.
    # No rebase onto main — the branch is self-contained by design.
    branch = "results/" + (os.getenv("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    code, text = run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"])
    output.append(text)
    output.append(f"results published on branch {branch!r}" if not code
                  else "!! push failed entirely; Results.md remains on the server only")
    return "\n".join(output)


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    budget_sec = TIME_BUDGET_HOURS * 3600

    log("waiting for the API...")
    if not wait_for_api():
        log("API did not become healthy; aborting")
        return 1

    health = http("GET", "/api/health", timeout=15)
    agent_info = {
        "provider": (health.get("ollama") or {}).get("provider"),
        "model": (health.get("ollama") or {}).get("model"),
        "base_url": (health.get("ollama") or {}).get("base_url"),
        "database": (health.get("postgres") or {}).get("detail"),
        "api_base": API_BASE,
    }
    log(f"agent: {agent_info}")

    stages = {}
    if "survey" in SKIP_STAGES or (health.get("workspace") or {}).get("ok"):
        log("workspace already surveyed; skipping survey")
        stages["survey"] = {"status": "skipped_existing"}
    else:
        stages["survey"] = run_job("survey", "/api/survey")
    stages.update(learning_loop("initial"))

    # The 6-hour budget covers the question blocks; bootstrap/stage time is excluded.
    campaign_started = time.monotonic()
    budget_deadline = campaign_started + budget_sec
    if judge.enabled():
        agent_info["judge_model"] = f"{judge.JUDGE_MODEL} (mode={JUDGE_MODE}, max_loops={JUDGE_MAX_LOOPS})"

    pack = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    blocks_report = []
    totals = {
        "questions": 0, "answered": 0, "clarified": 0, "pipeline_failed": 0, "skipped": 0,
        "rescued_retries": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
    }
    judge_reruns = 0

    for block in pack["blocks"]:
        block_started = time.monotonic()
        questions = list(block["questions"])
        eligible = [time.monotonic() <= budget_deadline for _ in questions]
        results, rescued_retries = run_block(questions, eligible, budget_deadline)

        if judge.enabled():
            for rerun in range(JUDGE_MAX_LOOPS + 1):
                incorrect = judge_block(results, agent_info)
                if not incorrect or rerun >= JUDGE_MAX_LOOPS or time.monotonic() > budget_deadline:
                    break
                judge_reruns += 1
                log(f"judge rejected {incorrect} answer(s) in {block['name']}; "
                    "running improvement stages and re-asking the block")
                for name, outcome in learning_loop(f"judge-triggered, {block['name']}").items():
                    stages[f"{name}#judge{judge_reruns}"] = outcome
                results, extra_rescued = run_block(questions, [True] * len(questions), budget_deadline)
                rescued_retries += extra_rescued

        blocks_report.append({
            "name": block["name"],
            "title": block["title"],
            "questions": results,
            "answered": 0,
            "clarified": 0,
            "pipeline_failed": 0,
            "skipped": 0,
            "rescued_retries": rescued_retries,
            "elapsed_min": round((time.monotonic() - block_started) / 60, 1),
        })
        totals["questions"] += len(results)
        totals["rescued_retries"] += rescued_retries
        for item in results:
            totals["tool_calls"] += item.get("tool_calls") or 0
            totals["prompt_tokens"] += item.get("prompt_tokens") or 0
            totals["completion_tokens"] += item.get("completion_tokens") or 0
        log(f"block {block['name']} done")

    background = collect_background_results(blocks_report)
    recount(blocks_report, totals)
    judge_summary = None
    if judge.enabled():
        judge_counts = {verdict: 0 for verdict in judge.VERDICTS}
        for block_report in blocks_report:
            for item in block_report["questions"]:
                verdict = (item.get("judge") or {}).get("verdict")
                if verdict in judge_counts:
                    judge_counts[verdict] += 1
        judge_summary = {
            "model": judge.JUDGE_MODEL,
            "base_url": judge.JUDGE_BASE_URL or agent_info.get("base_url") or "",
            "mode": JUDGE_MODE,
            "counts": judge_counts,
            "reruns": judge_reruns,
        }

    report = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_min": round((time.monotonic() - campaign_started) / 60, 1),
        "time_budget_hours": TIME_BUDGET_HOURS,
        "agent": f"{agent_info['provider']}/{agent_info['model']} via {agent_info['base_url']}, db={agent_info['database']}",
        "environment": agent_info,
        "stages": {name: {"status": value.get("status"), "error": (value.get("error") or "")[:200]}
                   for name, value in stages.items()},
        "blocks": blocks_report,
        "background": background,
        "judge": judge_summary,
        "totals": totals,
    }
    RESULTS_PATH.write_text(render_results(report), encoding="utf-8")
    log(f"Results.md written ({RESULTS_PATH})")
    log(git_publish())
    log("campaign finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
