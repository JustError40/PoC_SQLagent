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
from sqlagent.evaluator import default_corpus_path, evaluate_workspace, promote_candidate, rebuild_golden
from sqlagent.evolution import run_evolution
from sqlagent.explorer import run_exploration
from sqlagent.llm import OllamaClient, build_llm
from sqlagent.query_agent import ask
from sqlagent.surveyor import run_survey
from sqlagent.verification import verify_skill
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
        litellm_base_url=settings.litellm_base_url,
        litellm_api_key=settings.litellm_api_key,
        litellm_model=settings.litellm_model,
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
    explore_parser = subparsers.add_parser("explore", help="let the model iteratively probe the DB and extend its skill")
    explore_parser.add_argument("--rounds", type=int, default=None)
    explore_parser.add_argument("--probes-per-round", type=int, default=None)
    explore_parser.add_argument("--domain", default=None, help="scope exploration to one skill domain")
    subparsers.add_parser("optimize", help="improve each skill domain separately, then verify all templates")
    subparsers.add_parser("bootstrap", help="run survey + exploration when the workspace is not built yet")
    ask_parser = subparsers.add_parser("ask", help="answer one natural-language warehouse question")
    ask_parser.add_argument("question")
    evaluate_parser = subparsers.add_parser("evaluate", help="replay the regression corpus")
    evaluate_parser.add_argument("--workspace", type=Path, default=None)
    evaluate_parser.add_argument("--corpus", type=Path, default=None)
    subparsers.add_parser("golden", help="regenerate the deterministic golden corpus from the surveyed schema")
    subparsers.add_parser("verify", help="re-execute all skill templates and record their health into the manifest")
    lint_parser = subparsers.add_parser("lint", help="validate the skill manifest shape")
    lint_parser.add_argument("--fix", action="store_true", help="rewrite manifest.yaml in the canonical shape")
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
    if args.command == "explore":
        if not (workspace.root / "manifest.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        result = run_exploration(
            db,
            workspace,
            llm,
            rounds=args.rounds or settings.explorer_rounds,
            probes_per_round=args.probes_per_round or settings.explorer_probes_per_round,
            domain=args.domain,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "optimize":
        if not (workspace.root / "manifest.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        from sqlagent.explorer import optimize_skill

        print(json.dumps(optimize_skill(db, workspace, llm, probes_per_round=settings.explorer_probes_per_round), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "bootstrap":
        if (workspace.root / "manifest.yaml").exists():
            print(json.dumps({"status": "workspace_ready", "workspace": str(workspace.root)}, ensure_ascii=False))
            return 0
        survey = run_survey(db, workspace, llm)
        exploration = run_exploration(
            db,
            workspace,
            llm,
            rounds=settings.explorer_rounds,
            probes_per_round=settings.explorer_probes_per_round,
        )
        print(json.dumps({"status": "bootstrapped", "survey": survey, "exploration": exploration}, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "ask":
        if not (workspace.root / "manifest.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        print(json.dumps(ask(db, workspace, args.question, llm), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "evolve":
        print(json.dumps(run_evolution(workspace, args.min_trajectories, llm), ensure_ascii=False, indent=2))
        return 0
    if args.command == "golden":
        if not (workspace.root / "schema" / "tables.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        print(json.dumps(rebuild_golden(workspace), ensure_ascii=False, indent=2))
        return 0
    if args.command == "verify":
        if not (workspace.root / "manifest.yaml").exists():
            print("workspace is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        print(json.dumps(verify_skill(db, workspace), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "lint":
        raw = workspace.read_yaml("manifest.yaml", default=None)
        if raw is None:
            print("manifest.yaml is missing; run `python -m sqlagent survey` first", file=sys.stderr)
            return 2
        from sqlagent.workspace import lint_manifest, normalize_manifest

        issues = lint_manifest(raw)
        fixed = False
        if issues and args.fix:
            workspace.write_yaml("manifest.yaml", normalize_manifest(raw))
            fixed = True
        print(json.dumps({"issues": issues, "fixed": fixed}, ensure_ascii=False, indent=2))
        return 0 if not issues or fixed else 1
    if args.command == "evaluate":
        selected_workspace = Workspace((args.workspace or settings.workspace_path).resolve())
        corpus = (args.corpus or default_corpus_path(selected_workspace, settings.project_root)).resolve()
        report = evaluate_workspace(db, selected_workspace, corpus, llm)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str))
        return 0 if report.unsafe == 0 else 1
    if args.command == "promote":
        corpus = (args.corpus or default_corpus_path(workspace, settings.project_root)).resolve()
        result = promote_candidate(db, workspace, corpus, args.branch, llm)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["status"] == "promoted" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
