#!/usr/bin/env python3
"""Autonomous TPC-DS test campaign for the SQL agent PoC.

Runs fully unattended on the server:
1. waits for the API container to become healthy;
2. runs the learning stages (survey -> explore -> optimize -> evolve);
3. asks the question blocks from evals/test_campaign.json, timing every
   question and every block;
4. when 3+ questions of a block fail, repeats the learning loop and retries
   the failed questions once;
5. stops asking new questions after the global time budget (default 6 h);
6. writes Results.md and commits + pushes it to GitHub.

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
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = Path(os.getenv("CAMPAIGN_QUESTIONS", REPO_ROOT / "evals" / "test_campaign.json"))
RESULTS_PATH = Path(os.getenv("CAMPAIGN_RESULTS", REPO_ROOT / "Results.md"))
TIME_BUDGET_HOURS = float(os.getenv("CAMPAIGN_TIME_BUDGET_HOURS", "6"))
ASK_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_ASK_TIMEOUT_SEC", "1800"))
JOB_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_JOB_TIMEOUT_SEC", "3600"))
FAIL_THRESHOLD = int(os.getenv("CAMPAIGN_FAIL_THRESHOLD", "3"))
GIT_PUSH = os.getenv("CAMPAIGN_GIT_PUSH", "1").strip() not in {"0", "false", "no"}


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
        detail = exc.read().decode(errors="replace")[:500]
        return {"__http_error__": exc.code, "detail": detail}
    except Exception as exc:  # timeouts, connection resets — the campaign must go on
        return {"__http_error__": None, "detail": str(exc)[:500]}


def wait_for_api(timeout_sec: float = 600.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        health = http("GET", "/api/health", timeout=15)
        if health.get("ok"):
            return True
        time.sleep(10)
    return False


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
    outcomes["explore"] = run_job("explore", "/api/explore")
    outcomes["optimize"] = run_job("optimize", "/api/optimize")
    outcomes["evolve"] = run_job("evolve", "/api/evolve")
    outcomes["verify"] = run_job("verify", "/api/verify")
    log(f"learning loop ({rounds_note}) done: "
        + ", ".join(f"{k}={v.get('status')}" for k, v in outcomes.items()))
    return outcomes


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
            "status": "error",
            "error": f"HTTP {code}: {detail}" if code else f"transport: {detail}",
            "elapsed_sec": round(elapsed, 1),
        }
    error = response.get("error")
    clarification = bool(response.get("clarification"))
    return {
        "question": question,
        "status": "clarification" if clarification else ("error" if error else "ok"),
        "error": error or "",
        "elapsed_sec": round(elapsed, 1),
        "agent_elapsed_ms": (response.get("result") or {}).get("elapsed_ms"),
        "rows": len((response.get("result") or {}).get("rows") or []),
        "react_attempts": (response.get("react") or {}).get("attempts", 0),
        "route": response.get("route", ""),
        "template": response.get("template") or "",
        "sql": (response.get("sql") or "")[:600],
        "clarification": response.get("clarification") or "",
    }


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
        "| Block | Questions | OK | Clarification | Error | Retried OK | Block time |",
        "|---|---|---|---|---|---|---|",
    ]
    for block in report["blocks"]:
        lines.append(
            f"| {block['title']} | {len(block['questions'])} | {block['ok']} | "
            f"{block['clarification']} | {block['error']} | {block['retried_ok']} | {block['elapsed_min']} min |"
        )
    lines += [
        "",
        f"**Total: {report['totals']['ok']} ok / {report['totals']['clarification']} clarification / "
        f"{report['totals']['error']} error / {report['totals']['skipped']} skipped out of {report['totals']['questions']}**",
        "",
        "## Learning stages",
        "",
        "```",
        json.dumps(report["stages"], ensure_ascii=False, indent=2, default=str)[:4000],
        "```",
        "",
        "## Per-question detail",
        "",
    ]
    for block in report["blocks"]:
        lines += [
            f"### {block['title']} (`{block['name']}`)",
            "",
            "| # | Question | Status | Time, s | Agent rows | ReAct | Error |",
            "|---|---|---|---|---|---|---|",
        ]
        for index, item in enumerate(block["questions"], 1):
            error = (item.get("error") or "").replace("|", "\\|")[:120]
            lines.append(
                f"| {index} | {item['question']} | {item['status']} | {item.get('elapsed_sec', '-')} | "
                f"{item.get('rows', '-')} | {item.get('react_attempts', '-')} | {error} |"
            )
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
    commands = [
        ["git", "add", str(RESULTS_PATH.name)],
        ["git", "-c", "user.name=sqlagent-campaign", "-c", "user.email=sqlagent-campaign@localhost",
         "commit", "-m", f"test campaign results {datetime.now(timezone.utc).date().isoformat()}"],
    ]
    if GIT_PUSH:
        commands.append(["git", "push", "origin", "main"])
    output = []
    for command in commands:
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        output.append(f"$ {' '.join(command)}\n{completed.stdout}{completed.stderr}".strip())
        if completed.returncode and command[1] != "commit":  # empty commit is fine
            output.append(f"!! command failed with code {completed.returncode}")
            break
    return "\n".join(output)


def main() -> int:
    campaign_started = time.monotonic()
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
    if (health.get("workspace") or {}).get("ok"):
        log("workspace already surveyed; skipping survey")
        stages["survey"] = {"status": "skipped_existing"}
    else:
        stages["survey"] = run_job("survey", "/api/survey")
    stages.update(learning_loop("initial"))

    pack = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    blocks_report = []
    totals = {"questions": 0, "ok": 0, "clarification": 0, "error": 0, "skipped": 0}

    for block in pack["blocks"]:
        block_started = time.monotonic()
        results = []
        for question in block["questions"]:
            if time.monotonic() - campaign_started > budget_sec:
                results.append({"question": question, "status": "skipped", "error": "time budget exhausted"})
                continue
            log(f"asking [{block['name']}]: {question}")
            results.append(ask(question))
            log(f"  -> {results[-1]['status']} in {results[-1]['elapsed_sec']}s")

        failed = [item for item in results if item["status"] == "error"]
        retried_ok = 0
        if len(failed) >= FAIL_THRESHOLD and time.monotonic() - campaign_started < budget_sec:
            log(f"{len(failed)} errors in {block['name']}; repeating the learning loop and retrying")
            learning_loop(f"retry after {block['name']}")
            for item in failed:
                if time.monotonic() - campaign_started > budget_sec:
                    break
                log(f"retrying: {item['question']}")
                retry = ask(item["question"])
                retry["retried"] = True
                if retry["status"] == "ok":
                    retried_ok += 1
                results[results.index(item)] = retry
                log(f"  retry -> {retry['status']} in {retry['elapsed_sec']}s")

        counts = {"ok": 0, "clarification": 0, "error": 0, "skipped": 0}
        for item in results:
            counts[item["status"] if item["status"] in counts else "error"] += 1
        blocks_report.append({
            "name": block["name"],
            "title": block["title"],
            "questions": results,
            "ok": counts["ok"],
            "clarification": counts["clarification"],
            "error": counts["error"],
            "skipped": counts["skipped"],
            "retried_ok": retried_ok,
            "elapsed_min": round((time.monotonic() - block_started) / 60, 1),
        })
        totals["questions"] += len(results)
        for key in ("ok", "clarification", "error", "skipped"):
            totals[key] += counts[key]
        log(f"block {block['name']} done: {counts}")

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
        "totals": totals,
    }
    RESULTS_PATH.write_text(render_results(report), encoding="utf-8")
    log(f"Results.md written ({RESULTS_PATH})")
    log(git_publish())
    log("campaign finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
