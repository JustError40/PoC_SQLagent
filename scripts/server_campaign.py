#!/usr/bin/env python3
"""Multi-DB self-evolution campaign for the external server.

Unattended multi-day runner. For every configured database it:
1. loads the official BIRD PostgreSQL extract into the postgres container
   (CREATE DATABASE if missing, psql restore if the schema is absent);
2. recreates the api container with TARGET_DB=<database> and a fresh
   RUN_ID=<run_id> workspace, then waits for bootstrap+survey to finish;
3. scores the golden corpus once WITHOUT learning stages (control run — the
   noise baseline of the model at its configured temperature);
4. runs N evolution iterations on the SAME workspace: ask+score every corpus
   question, then the agent's own learning stages (explore/optimize/evolve/
   promote/verify). Golden answers are the scoring reference only and are never
   fed back to the agent;
5. snapshots the evolved workspace and commits every run separately.

Everything runs on a campaign branch created by this script
(campaign/<YYYYMMDD-HHMMSS>): one commit per control run, per iteration, per
workspace snapshot and one for the final aggregation. Push is controlled by
CAMPAIGN_GIT_PUSH (default 1).

Scoring splits failures by cause so harness failures are never confused with
semantically wrong answers (correct / wrong_answer / compare_error /
failed_schema / failed_react / failed_llm / failed_other).

Outputs:
- experiment_results/<db_id>/report.md + report.json   (per-DB iterations)
- experiment_results/<db_id>/workspace/                (evolved skill snapshot)
- Results_evolution.md + evolution_summary.json        (cross-DB aggregation)

Run on the server:  uv run python scripts/server_campaign.py
Requires: docker compose stack files, .env with POSTGRES_PASSWORD etc.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import evolution_loop as loop  # imported as a package (tests)
except ImportError:  # run directly as scripts/server_campaign.py on the server
    import evolution_loop as loop

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "docker-compose.yml")
RESULTS_DIR = Path(os.getenv("CAMPAIGN_RESULTS_DIR", REPO_ROOT / "experiment_results"))
AGG_MD = Path(os.getenv("CAMPAIGN_AGG_MD", REPO_ROOT / "Results_evolution.md"))
AGG_JSON = Path(os.getenv("CAMPAIGN_AGG_JSON", REPO_ROOT / "evolution_summary.json"))
GIT_PUSH = os.getenv("CAMPAIGN_GIT_PUSH", "1").strip() not in {"0", "false", "no"}
HEALTH_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_HEALTH_TIMEOUT_SEC", "0"))  # 0 = wait forever

CAMPAIGN_TS = os.getenv("CAMPAIGN_TS") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
BRANCH = os.getenv("CAMPAIGN_BRANCH") or f"campaign/{CAMPAIGN_TS}"

# Default corpus: BIRD mini-dev databases with golden packs committed under
# evals/ and official PostgreSQL extracts committed under db_seed/bird/.
DEFAULT_DBS = [
    {"db_id": "california_schools"},
    {"db_id": "debit_card_specializing"},
    {"db_id": "student_club"},
]


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def sh(command: list[str], env_extra: dict | None = None, check: bool = False) -> tuple[int, str]:
    env = {**os.environ, **(env_extra or {})}
    completed = subprocess.run(
        command, cwd=REPO_ROOT, env=env, capture_output=True, text=True
    )
    out = f"$ {' '.join(command)}\n{completed.stdout}{completed.stderr}".strip()
    if check and completed.returncode:
        raise RuntimeError(out)
    return completed.returncode, out


def dotenv() -> dict:
    """Minimal .env reader for the scoring DSN (compose reads it on its own)."""
    values = {}
    path = REPO_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def compose(*args: str, env_extra: dict | None = None, check: bool = False) -> tuple[int, str]:
    return sh(["docker", "compose", "-f", COMPOSE_FILE, *args], env_extra=env_extra, check=check)


# ---------------------------------------------------------------- database


def load_database(cfg: dict) -> None:
    """Create the database and restore the extract if the schema is missing."""
    database = cfg["database"]
    user = dotenv().get("POSTGRES_USER", "warehouse")
    code, out = compose(
        "exec", "-T", "postgres", "psql", "-U", user, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{database}'",
    )
    if "1" not in out:
        log(f"{database}: creating database")
        compose("exec", "-T", "postgres", "psql", "-U", user, "-d", "postgres",
                "-c", f"CREATE DATABASE {database}", check=True)
    code, out = compose(
        "exec", "-T", "postgres", "psql", "-U", user, "-d", database, "-tAc",
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'",
    )
    table_count = next((int(line) for line in out.splitlines() if line.strip().isdigit()), 0)
    if table_count:
        log(f"{database}: already loaded ({table_count} tables); skipping restore")
        return
    dump = REPO_ROOT / cfg["dump"]
    log(f"{database}: restoring {dump}")
    with dump.open("rb") as stream:
        env = {**os.environ}
        completed = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "postgres",
             "psql", "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1", "-q"],
            cwd=REPO_ROOT, env=env, stdin=stream, capture_output=True, text=True,
        )
    if completed.returncode:
        raise RuntimeError(f"restore failed for {database}: {completed.stderr[-2000:]}")
    log(f"{database}: restore done")


def recreate_api(cfg: dict) -> None:
    env = {"TARGET_DB": cfg["database"], "RUN_ID": cfg["run_id"]}
    log(f"recreating api: TARGET_DB={cfg['database']} RUN_ID={cfg['run_id']}")
    compose("up", "-d", "--force-recreate", "api", env_extra=env, check=True)


def wait_for_api() -> None:
    started = time.monotonic()
    while True:
        health = loop.http("GET", "/api/health", timeout=15)
        if health.get("ok"):
            log(f"api healthy: workspace={(health.get('workspace') or {}).get('path')}")
            return
        if HEALTH_TIMEOUT_SEC and time.monotonic() - started > HEALTH_TIMEOUT_SEC:
            raise RuntimeError(f"API not healthy after {HEALTH_TIMEOUT_SEC}s: {health}")
        time.sleep(30)


# ---------------------------------------------------------------- git


def git(*args: str) -> tuple[int, str]:
    return sh(["git", "-c", "user.name=sqlagent-campaign",
               "-c", "user.email=sqlagent-campaign@localhost", *args])


def git_branch_setup() -> None:
    code, out = git("rev-parse", "--is-inside-work-tree")
    if code:
        log("!! not a git repository; results stay on disk only")
        return
    code, out = git("checkout", "-b", BRANCH)
    if code:
        # Branch exists (rerun of the same campaign): just switch to it.
        git("checkout", BRANCH)
    log(f"git: on branch {BRANCH}")


def git_commit(paths: list[Path], message: str) -> None:
    existing = [str(path.relative_to(REPO_ROOT)) for path in paths if path.exists()]
    if not existing:
        return
    git("add", *existing)
    code, out = git("commit", "-m", message)
    if code and "nothing to commit" in out:
        log(f"git: {message} — nothing to commit")
        return
    log(f"git: committed '{message}'")
    if GIT_PUSH:
        code, out = git("push", "-u", "origin", BRANCH)
        log(f"git: push {'ok' if not code else 'FAILED (results stay local)'}")


# ---------------------------------------------------------------- experiment


def scoring_dsn(database: str) -> str:
    env = dotenv()
    user = env.get("POSTGRES_USER", "warehouse")
    password = env.get("POSTGRES_PASSWORD", "warehouse")
    port = env.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@localhost:{port}/{database}"


def snapshot_workspace(cfg: dict) -> Path | None:
    src = REPO_ROOT / "runs" / cfg["run_id"] / "skill"
    if not src.exists():
        return None
    dst = RESULTS_DIR / cfg["db_id"] / "workspace"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return dst


def run_db(cfg: dict, iterations: int) -> dict:
    db_id = cfg["db_id"]
    log(f"===== {db_id}: loading database =====")
    load_database(cfg)
    recreate_api(cfg)
    wait_for_api()

    corpus = [json.loads(line) for line in (REPO_ROOT / cfg["golden"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    report_json = RESULTS_DIR / db_id / "report.json"
    report_md = RESULTS_DIR / db_id / "report.md"
    report_json.parent.mkdir(parents=True, exist_ok=True)

    from sqlagent.db import Database

    db = Database(scoring_dsn(cfg["database"]))
    rows = []
    total_runs = iterations + 1  # control + evolution iterations
    for run in range(total_runs):
        is_control = run == 0
        label = "control" if is_control else f"iteration {run}"
        started = time.monotonic()
        scored = loop.score_iteration(db, corpus, cfg["concurrency"])
        stages = {}
        if not is_control:
            time.sleep(loop.SETTLE_SEC)
            for stage in ("explore", "optimize", "evolve", "promote", "verify"):
                stages[stage] = loop.run_stage(stage)
                log(f"{db_id} {label}: {stage} -> {stages[stage]}")
        elapsed_min = round((time.monotonic() - started) / 60, 1)
        row = {"run": label, "elapsed_min": elapsed_min, "stages": stages,
               "counts": scored["counts"], "details": scored["details"]}
        rows.append(row)
        log(f"{db_id} {label} done in {elapsed_min} min: {scored['counts']}")

        report_json.write_text(json.dumps(
            {"db_id": db_id, "run_id": cfg["run_id"], "corpus": cfg["golden"],
             "questions": len(corpus), "rows": rows},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        report_md.write_text(render_db(cfg, rows, len(corpus)), encoding="utf-8")
        git_commit([report_json, report_md], f"campaign: {db_id} {label}")

    snapshot = snapshot_workspace(cfg)
    if snapshot:
        git_commit([snapshot], f"campaign: {db_id} final workspace snapshot")
    return {"db_id": db_id, "run_id": cfg["run_id"], "questions": len(corpus), "rows": rows}


def render_db(cfg: dict, rows: list[dict], questions: int) -> str:
    lines = [
        f"# Evolution experiment — {cfg['db_id']}",
        "",
        f"- Corpus: {cfg['golden']} ({questions} questions)",
        f"- Run ID (workspace): {cfg['run_id']}",
        f"- Database: {cfg['database']}",
        "- Control = run without learning stages (model noise baseline)",
        "",
        "| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Time, min |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        c = row["counts"]
        lines.append(
            f"| {row['run']} | {c.get('correct', 0)} | {c.get('wrong_answer', 0)} | {c.get('compare_error', 0)} | "
            f"{c.get('clarified', 0)} | {c.get('failed_schema', 0)} | {c.get('failed_react', 0)} | "
            f"{c.get('failed_llm', 0)} | {c.get('failed_other', 0)} | {row['elapsed_min']} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- aggregation


def aggregate(results: list[dict]) -> tuple[str, dict]:
    summary = {"campaign_ts": CAMPAIGN_TS, "branch": BRANCH, "dbs": []}
    lines = [
        "# Multi-DB self-evolution campaign — aggregated results",
        "",
        f"- Campaign: {CAMPAIGN_TS} (branch `{BRANCH}`)",
        "- Golden answers were used for scoring ONLY; the agent learned exclusively "
        "from its own failures via the standard learning stages.",
        "- control = corpus run without learning stages (noise baseline).",
        "",
    ]
    for result in results:
        rows = result["rows"]
        db_entry = {"db_id": result["db_id"], "run_id": result["run_id"],
                    "questions": result["questions"], "rows": rows}
        summary["dbs"].append(db_entry)
        lines += [
            f"## {result['db_id']} ({result['questions']} questions)",
            "",
            "| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema | Fail: react | Fail: LLM | Fail: other |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            c = row["counts"]
            lines.append(
                f"| {row['run']} | {c.get('correct', 0)} | {c.get('wrong_answer', 0)} | "
                f"{c.get('compare_error', 0)} | {c.get('clarified', 0)} | {c.get('failed_schema', 0)} | "
                f"{c.get('failed_react', 0)} | {c.get('failed_llm', 0)} | {c.get('failed_other', 0)} |"
            )
        first, last = rows[0]["counts"], rows[-1]["counts"]
        delta = last.get("correct", 0) - first.get("correct", 0)
        lines += [
            "",
            f"Baseline vs final: correct {first.get('correct', 0)} → {last.get('correct', 0)} "
            f"({'+' if delta >= 0 else ''}{delta}).",
            "",
        ]
    return "\n".join(lines), summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=int(os.getenv("CAMPAIGN_ITERATIONS", "5")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("LOOP_CONCURRENCY", "4")))
    parser.add_argument("--config", type=Path, default=None,
                        help="JSON list of {db_id, database, dump, golden}; default: 3 BIRD DBs")
    parser.add_argument("--only", nargs="*", default=None, help="run only these db_id values")
    args = parser.parse_args()

    if args.config:
        dbs = json.loads(args.config.read_text(encoding="utf-8"))
    else:
        dbs = list(DEFAULT_DBS)
    for cfg in dbs:
        cfg.setdefault("database", cfg["db_id"])
        cfg.setdefault("dump", f"db_seed/bird/{cfg['db_id']}.pg.sql")
        cfg.setdefault("golden", f"evals/bird_{cfg['db_id']}.golden.jsonl")
        cfg.setdefault("run_id", f"server-{cfg['db_id']}-{CAMPAIGN_TS}")
        cfg.setdefault("concurrency", args.concurrency)
    if args.only:
        dbs = [cfg for cfg in dbs if cfg["db_id"] in args.only]
    if not dbs:
        raise SystemExit("no databases configured")

    git_branch_setup()
    manifest = RESULTS_DIR / "campaign_manifest.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "campaign_ts": CAMPAIGN_TS, "branch": BRANCH, "iterations": args.iterations,
        "dbs": dbs, "started_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    git_commit([manifest], f"campaign {CAMPAIGN_TS}: manifest ({len(dbs)} dbs, {args.iterations} iterations)")

    results = []
    for cfg in dbs:
        try:
            results.append(run_db(cfg, args.iterations))
        except Exception as exc:  # stop rule: record and move to the next db
            log(f"!! {cfg['db_id']} aborted: {exc}")
            results.append({"db_id": cfg["db_id"], "run_id": cfg["run_id"],
                            "questions": 0, "rows": [], "error": str(exc)[:500]})

    md, summary = aggregate(results)
    AGG_MD.write_text(md, encoding="utf-8")
    AGG_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    git_commit([AGG_MD, AGG_JSON], f"campaign {CAMPAIGN_TS}: aggregated results")
    log(f"campaign finished; aggregated report at {AGG_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
