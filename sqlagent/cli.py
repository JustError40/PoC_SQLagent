from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from db_seed.seed import seed_database
from db_seed.demo import load_dvdrental
from db_seed.tpcds import bootstrap_tpcds

from sqlagent.config import Settings
from sqlagent.db import Database
from sqlagent.evaluator import evaluate_workspace, promote_candidate
from sqlagent.evolution import run_evolution
from sqlagent.llm import OllamaClient, build_llm
from sqlagent.query_agent import ask
from sqlagent.surveyor import run_survey
from sqlagent.workspace import Workspace


def _runtime(settings: Settings) -> tuple[Database, Workspace, OllamaClient]:
    workspace = Workspace(settings.workspace_path)
    db = Database(settings.database_url, settings.max_result_rows, settings.statement_timeout_ms)
    llm = build_llm(
        provider=settings.llm_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        opencode_go_base_url=settings.opencode_go_base_url,
        opencode_go_api_key=settings.opencode_go_api_key,
        opencode_go_model=settings.opencode_go_model,
        cache_dir=workspace.root / ".cache" / "llm",
    )
    return db, workspace, llm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sqlagent", description="Self-evolving SQL-agent PoC")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="recreate and fill the synthetic PostgreSQL warehouse")
    subparsers.add_parser("demo-load", help="restore the downloaded dvdrental dump into a separate database")
    tpcds_parser = subparsers.add_parser("tpcds-bootstrap", help="generate/load TPC-DS into the separate tpcds database")
    tpcds_parser.add_argument("--scale", type=int, default=None)
    tpcds_parser.add_argument("--data-dir", type=Path, default=None)
    tpcds_parser.add_argument("--toolkit", type=Path, default=None)
    tpcds_parser.add_argument("--force", action="store_true")
    tpcds_parser.add_argument("--replace", action="store_true")
    subparsers.add_parser("survey", help="inventory/profile the DB and generate the skill workspace")
    ask_parser = subparsers.add_parser("ask", help="answer one natural-language warehouse question")
    ask_parser.add_argument("question")
    evaluate_parser = subparsers.add_parser("evaluate", help="replay the regression corpus")
    evaluate_parser.add_argument("--workspace", type=Path, default=None)
    evaluate_parser.add_argument("--corpus", type=Path, default=None)
    promote_parser = subparsers.add_parser("promote", help="evaluate and promote the current evolution candidate")
    promote_parser.add_argument("--branch", default=None)
    promote_parser.add_argument("--corpus", type=Path, default=None)
    evolve_parser = subparsers.add_parser("evolve", help="create an evolution candidate from trajectories")
    evolve_parser.add_argument("--min-trajectories", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.command == "seed":
        print(json.dumps(seed_database(settings.database_url, settings.seed_orders), ensure_ascii=False, indent=2))
        return 0
    if args.command == "demo-load":
        print(json.dumps(load_dvdrental(settings.database_url), ensure_ascii=False, indent=2))
        return 0
    if args.command == "tpcds-bootstrap":
        data_dir = (args.data_dir or settings.tpcds_data_path).resolve()
        toolkit = (args.toolkit or settings.tpcds_toolkit_path).resolve()
        result = bootstrap_tpcds(settings.database_url, args.scale or settings.tpcds_scale, data_dir, toolkit, args.force, args.replace)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    db, workspace, llm = _runtime(settings)
    if args.command == "survey":
        print(json.dumps(run_survey(db, workspace, llm), ensure_ascii=False, indent=2))
        return 0
    if args.command == "ask":
        if not (workspace.root / "manifest.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        print(json.dumps(ask(db, workspace, args.question, llm), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "evolve":
        print(json.dumps(run_evolution(workspace, args.min_trajectories), ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate":
        selected_workspace = Workspace((args.workspace or settings.workspace_path).resolve())
        corpus = (args.corpus or settings.project_root / "evals" / "regression.jsonl").resolve()
        report = evaluate_workspace(db, selected_workspace, corpus, llm)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if report.unsafe == 0 else 1
    if args.command == "promote":
        corpus = (args.corpus or settings.project_root / "evals" / "regression.jsonl").resolve()
        result = promote_candidate(db, workspace, corpus, args.branch, llm)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["status"] == "promoted" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
