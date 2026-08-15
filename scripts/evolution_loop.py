#!/usr/bin/env python3
"""N-iteration self-evolution experiment driver (local laptop stack, not committed).

Each iteration:
1. asks every corpus question through the API;
2. scores "answered" items against the golden SQL (result-set equivalence via
   compare_queries_full) — the reference is used for measurement ONLY and is
   never fed back into the agent;
3. buckets failures by cause, so harness failures are never confused with
   semantically wrong answers:
     - failed_schema  — llm_schema_violation (model broke the JSON contract)
     - failed_react   — react_exhausted (repair budget spent on SQL errors)
     - failed_llm     — llm_timeout / llm_transport_error
     - failed_other   — anything else
     - compare_error  — answer exists but could not be compared to the golden
4. runs the agent's own learning stages (explore/optimize/evolve/promote/verify)
   unless --control is given;
5. appends a per-iteration row to the report.

Run: uv run python scripts/evolution_loop.py --corpus evals/bird_<db>.golden.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://warehouse:warehouse@localhost:5433/bird"
)
ASK_TIMEOUT_SEC = float(os.getenv("LOOP_ASK_TIMEOUT_SEC", "1800"))
JOB_TIMEOUT_SEC = float(os.getenv("LOOP_JOB_TIMEOUT_SEC", "3600"))
# Let the background failure learner digest fresh failures before evolve runs.
SETTLE_SEC = float(os.getenv("LOOP_SETTLE_SEC", "30"))

SCHEMA_ERROR_TYPES = {"llm_schema_violation", "serialization_failed"}
REACT_ERROR_TYPES = {"react_exhausted", "sql_validation_failed"}
LLM_ERROR_TYPES = {"llm_timeout", "llm_transport_error"}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def http(method: str, path: str, payload: dict | None = None, timeout: float = 60.0) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        API_BASE + path, data=body, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        return {"__error__": str(exc)[:500]}


def ask(question: str) -> dict:
    response = http("POST", "/api/ask", {"question": question}, timeout=ASK_TIMEOUT_SEC)
    error = response.get("error") or {}
    if isinstance(error, str):
        error = {"type": "internal_error", "message": error}
    return {
        "question": question,
        "status": str(response.get("status") or ("pipeline_failed" if error else "answered")),
        "error_type": error.get("type"),
        "sql": response.get("sql") or "",
    }


def run_stage(name: str) -> str:
    started = http("POST", f"/api/{name}", timeout=60)
    job_id = started.get("job_id")
    if not job_id:
        return f"start_failed: {started.get('__error__', started)}"
    deadline = time.monotonic() + JOB_TIMEOUT_SEC
    while time.monotonic() < deadline:
        time.sleep(10)
        job = http("GET", f"/api/jobs/{job_id}", timeout=30)
        status = job.get("status")
        if status and status != "running":
            result_status = (job.get("result") or {}).get("status") if isinstance(job.get("result"), dict) else None
            return f"{status}:{result_status}" if result_status else str(status)
    return "timeout"


def score_iteration(db, corpus: list[dict], concurrency: int) -> dict:
    with ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix="loop-ask") as pool:
        answers = list(pool.map(lambda item: ask(item["question"]), corpus))

    counts = {
        "correct": 0, "wrong_answer": 0, "compare_error": 0, "clarified": 0,
        "failed_schema": 0, "failed_react": 0, "failed_llm": 0, "failed_other": 0,
    }
    details = []
    for item, answer in zip(corpus, answers):
        verdict = answer["status"]
        if answer["status"] == "answered":
            if not answer["sql"] or not item.get("golden_sql"):
                verdict = "compare_error"
            else:
                try:
                    verdict = "correct" if db.compare_queries_full(item["golden_sql"], answer["sql"]).equivalent else "wrong_answer"
                except Exception:
                    verdict = "compare_error"
        elif answer["status"] == "pipeline_failed":
            error_type = str(answer.get("error_type") or "")
            if error_type in SCHEMA_ERROR_TYPES:
                verdict = "failed_schema"
            elif error_type in REACT_ERROR_TYPES:
                verdict = "failed_react"
            elif error_type in LLM_ERROR_TYPES:
                verdict = "failed_llm"
            else:
                verdict = "failed_other"
        counts[verdict] = counts.get(verdict, 0) + 1
        details.append({"id": item["id"], "verdict": verdict, "error_type": answer.get("error_type")})
    return {"counts": counts, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="golden jsonl: id/question/golden_sql")
    parser.add_argument("--iterations", type=int, default=int(os.getenv("LOOP_ITERATIONS", "10")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("LOOP_CONCURRENCY", "12")))
    parser.add_argument("--control", action="store_true", help="skip learning stages (noise baseline)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    from sqlagent.db import Database

    corpus = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = args.out or Path("runs/local") / f"evolution_loop_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    db = Database(DATABASE_URL)

    health = http("GET", "/api/health", timeout=15)
    if not health.get("ok"):
        raise SystemExit(f"API is not healthy at {API_BASE}: {health}")

    rows = []
    for iteration in range(1, args.iterations + 1):
        started = time.monotonic()
        scored = score_iteration(db, corpus, args.concurrency)
        stages = {}
        if not args.control and iteration < args.iterations:
            time.sleep(SETTLE_SEC)
            for stage in ("explore", "optimize", "evolve", "promote", "verify"):
                stages[stage] = run_stage(stage)
                log(f"iteration {iteration}: {stage} -> {stages[stage]}")
        elapsed_min = round((time.monotonic() - started) / 60, 1)
        rows.append({"iteration": iteration, "elapsed_min": elapsed_min, "stages": stages, **scored["counts"]})
        log(f"iteration {iteration} done in {elapsed_min} min: {scored['counts']}")
        out.write_text(render(args, corpus, rows), encoding="utf-8")
    log(f"report written to {out}")
    return 0


def render(args: argparse.Namespace, corpus: list[dict], rows: list[dict]) -> str:
    lines = [
        "# Evolution loop experiment",
        "",
        f"- Corpus: {args.corpus} ({len(corpus)} questions)",
        f"- Iterations: {len(rows)} (control={args.control})",
        f"- API: {API_BASE}, DB: {DATABASE_URL}",
        "",
        "| Iter | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Time, min |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['iteration']} | {row['correct']} | {row['wrong_answer']} | {row['compare_error']} | "
            f"{row['clarified']} | {row['failed_schema']} | {row['failed_react']} | "
            f"{row['failed_llm']} | {row['failed_other']} | {row['elapsed_min']} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
