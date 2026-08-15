"""Iterative self-exploration loop: the model probes the database through the
same read-only safety gates as the query agent and writes verified knowledge
(templates, dangerous joins, learned rules) back into its own skill workspace."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from sqlagent.db import Database, validate_read_only
from sqlagent.llm import LLMUnavailable, OllamaClient
from sqlagent.sqllint import lint_sql, schema_from_tables_yaml
from sqlagent.trajectories import append_trajectory, read_trajectories
from sqlagent.workspace import Workspace


class ExplorerState(TypedDict, total=False):
    workspace_path: str
    rounds: int
    probes_per_round: int
    round_index: int
    probes: list[dict[str, Any]]
    results: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    written: list[str]
    stop_reason: str


class _LintFailure(ValueError):
    """Probe SQL referenced identifiers the skill schema does not know."""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "probe"


def _exploration_log_path(workspace: Workspace) -> Path:
    return workspace.root / "experience" / "exploration.jsonl"


def _reflections_log_path(workspace: Workspace) -> Path:
    return workspace.root / "experience" / "reflections.jsonl"


def _lint_schema(workspace: Workspace) -> dict[str, list[str]]:
    tables = (workspace.read_yaml("schema/tables.yaml", default={}) or {}).get("tables", [])
    return schema_from_tables_yaml(tables)


def _identifier_notes(workspace: Workspace) -> list[dict[str, Any]]:
    return (workspace.read_yaml("schema/identifier_notes.yaml", default={}) or {}).get("notes", [])


def _recent_lessons(workspace: Workspace, limit: int = 5) -> list[str]:
    log = read_trajectories(_reflections_log_path(workspace))
    lessons = [lesson for item in log for lesson in item.get("lessons", [])]
    return lessons[-limit:]


def _save_identifier_notes(workspace: Workspace, corrections: list[dict[str, Any]]) -> None:
    if not corrections:
        return
    path = "schema/identifier_notes.yaml"
    data = workspace.read_yaml(path, default={"notes": []}) or {"notes": []}
    notes = data.setdefault("notes", [])
    known = {(note.get("wrong"), note.get("correct")) for note in notes}
    for correction in corrections:
        if (correction.get("wrong"), correction.get("correct")) not in known:
            notes.append(correction)
    workspace.write_yaml(path, data)


def _extract_corrections(failed_sql: str, error: str, fixed_sql: str) -> list[dict[str, Any]]:
    """Pull wrong -> correct identifier pairs out of a PostgreSQL error and its repair."""

    wrong_match = re.search(r'column "?(?P<wrong>[a-zA-Z_][\w.]*)"? does not exist', error)
    hint_match = re.search(r'Perhaps you meant to reference the column "(?P<correct>[\w.]+)"', error)
    if not wrong_match or not hint_match:
        return []
    wrong = wrong_match.group("wrong").split(".")[-1]
    correct = hint_match.group("correct").split(".")[-1]
    if wrong == correct or wrong not in failed_sql or correct not in fixed_sql:
        return []
    return [{"wrong": wrong, "correct": correct, "source": "repair"}]


def _manifest_context(workspace: Workspace) -> dict[str, Any]:
    manifest = workspace.read_manifest()
    return {
        "tables": manifest.get("tables", []),
        "domains": manifest.get("domains", {}),
        "templates": manifest.get("templates", {}),
        "dangerous_joins": (workspace.read_yaml("relationships/dangerous_joins.yaml", default={}) or {}).get("joins", []),
        "verified_joins": (workspace.read_yaml("relationships/verified_joins.yaml", default={}) or {}).get("joins", []),
    }


def _schema_context(workspace: Workspace, max_columns: int = 60) -> dict[str, Any]:
    """Exact table/column names so the model never has to guess identifiers."""

    tables = (workspace.read_yaml("schema/tables.yaml", default={}) or {}).get("tables", [])
    return {
        table["name"]: {
            "grain": table.get("grain", ""),
            "columns": [column["column_name"] for column in table.get("columns", [])][:max_columns],
        }
        for table in tables
        if isinstance(table, dict) and table.get("name")
    }


def plan_node(state: ExplorerState, *, workspace: Workspace, llm: OllamaClient | None) -> dict[str, Any]:
    if llm is None:
        return {"stop_reason": "llm_unavailable", "probes": []}
    log = read_trajectories(_exploration_log_path(workspace))
    skill = _manifest_context(workspace)
    schema = _schema_context(workspace)
    domain = str(state.get("domain") or "")
    if domain:
        # Domain-scoped exploration: the model only sees the sub-skill's tables,
        # exactly like the query agent loads only the routed skill parts.
        domain_tables = set((skill.get("domains") or {}).get(domain, []))
        if domain_tables:
            schema = {name: info for name, info in schema.items() if name in domain_tables}
    context = {
        "skill": skill,
        "schema": schema,
        "identifier_notes": _identifier_notes(workspace),
        "your_lessons": _recent_lessons(workspace),
        "previous_probes": [
            {"question": item.get("question"), "status": item.get("status"), "error": item.get("error")}
            for item in log[-5:]
        ],
    }
    limit = state["probes_per_round"]
    focus = f" Focus only on the subject area '{domain}' — the schema map lists exactly its tables." if domain else ""
    try:
        answer = llm.chat_json(
            "You are exploring a PostgreSQL database to improve your own skill workspace."
            + focus
            + " Propose up to "
            f"{limit} read-only probe tasks that would teach you something reusable: verify a join or "
            "fanout hypothesis, profile an important column, or draft a reusable metric template. "
            "Keep each probe simple: prefer single-table aggregations, and join at most two tables "
            "using only the exact column pairs listed in verified_joins. "
            "Do not repeat previous probes. Use only the exact table and column names from the schema — "
            "never guess identifiers; respect identifier_notes (identifiers you got wrong before) and "
            "follow your_lessons from earlier reflection rounds. "
            'Return JSON {"probes": [{"name": snake_case, "question": what the probe answers, '
            '"sql": one PostgreSQL SELECT/WITH}]}.',
            json.dumps(context, ensure_ascii=False, default=str),
        )
    except LLMUnavailable as exc:
        return {"stop_reason": f"llm_unavailable: {exc}", "probes": []}
    probes: list[dict[str, Any]] = []
    for item in (answer.get("probes") or [])[:limit]:
        if not isinstance(item, dict) or not item.get("sql"):
            continue
        probes.append(
            {
                "name": _slug(str(item.get("name") or f"probe_{len(probes)}")),
                "question": str(item.get("question") or ""),
                "sql": str(item["sql"]),
            }
        )
    if not probes:
        return {"stop_reason": "no_probes_planned"}
    return {"probes": probes}


def _run_probe(db: Database, record: dict[str, Any]) -> dict[str, Any]:
    query = validate_read_only(record["sql"])
    record["sql"] = query
    record["explain"] = db.explain(query)
    result = db.execute(query)
    record.update(
        {
            "status": "ok",
            "columns": result.columns,
            "sample_rows": result.rows[:3],
            "rows": len(result.rows),
            "elapsed_ms": result.elapsed_ms,
        }
    )
    return record


def act_node(state: ExplorerState, *, db: Database, workspace: Workspace, llm: OllamaClient | None) -> dict[str, Any]:
    log_path = _exploration_log_path(workspace)
    lint_schema = _lint_schema(workspace)

    def execute_probe(probe: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        local_corrections: list[dict[str, Any]] = []
        record: dict[str, Any] = {
            "round": state.get("round_index", 0),
            "name": probe["name"],
            "question": probe["question"],
            "sql": probe["sql"],
        }
        try:
            query = validate_read_only(probe["sql"])
            if lint_schema:
                problems = lint_sql(query, lint_schema)
                if problems:
                    raise _LintFailure("; ".join(problems))
            record["sql"] = query
            record = _run_probe(db, record)
        except Exception as exc:  # DB/safety/lint errors are observations, not crashes
            record.update({"status": "error", "error": str(exc)[:500], "error_source": "lint" if isinstance(exc, _LintFailure) else "database"})
            if llm is not None:
                repaired = _repair_probe(db, workspace, llm, probe, record["error"])
                if repaired is not None:
                    found = _extract_corrections(probe["sql"], record["error"], repaired["sql"])
                    if found:
                        local_corrections.extend(found)
                    record = repaired
                    record.update({"round": record.get("round", state.get("round_index", 0)), "name": probe["name"], "question": probe["question"], "repaired": True})
        return record, local_corrections

    probes = list(state.get("probes", []))
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(probes))), thread_name_prefix="explorer-probe") as pool:
        completed = list(pool.map(execute_probe, probes))
    # Only artifact/log writes are serialized; the results retain planner order.
    results = [item[0] for item in completed]
    corrections = [correction for _, found in completed for correction in found]
    for record, found in completed:
        if found:
            append_trajectory(
                workspace.root / "experience" / "error_corrections.jsonl",
                {"round": state.get("round_index", 0), "corrections": found},
            )
        append_trajectory(log_path, record)
    _save_identifier_notes(workspace, corrections)
    return {"results": results, "corrections": corrections}


def _repair_probe(db: Database, workspace: Workspace, llm: OllamaClient, probe: dict[str, Any], error: str) -> dict[str, Any] | None:
    """One bounded repair attempt for a failed probe, guided by the exact schema."""

    try:
        answer = llm.chat_json(
            "A read-only probe against a PostgreSQL database failed. Fix the SQL using only the exact "
            "table and column names from the schema. Return JSON {\"sql\": corrected SELECT/WITH}.",
            json.dumps(
                {
                    "question": probe["question"],
                    "failed_sql": probe["sql"],
                    "error": error,
                    "schema": _schema_context(workspace),
                },
                ensure_ascii=False,
                default=str,
            ),
        )
    except LLMUnavailable:
        return None
    fixed = str(answer.get("sql") or "").strip()
    if not fixed:
        return None
    record: dict[str, Any] = {"sql": fixed}
    try:
        return _run_probe(db, record)
    except Exception:
        return None


def _apply_template(workspace: Workspace, db: Database, artifact: dict[str, Any]) -> str | None:
    sql_text = str(artifact.get("sql") or "")
    if not sql_text:
        return None
    try:
        query = validate_read_only(sql_text)
        db.explain(query)
        db.execute(query)  # a template earns its place only by running cleanly against the real DB
    except Exception:
        return None
    name = _slug(str(artifact.get("name") or "metric"))
    manifest = workspace.read_manifest()
    templates = manifest.setdefault("templates", {})
    if name in templates:
        return None
    path = f"templates/{name}.sql"
    workspace.write_text(path, query + ";\n")
    templates[name] = {
        "path": path,
        "description": str(artifact.get("description") or artifact.get("question") or name),
        "grain": str(artifact.get("grain") or ""),
    }
    workspace.write_yaml("manifest.yaml", manifest)
    return path


def _apply_verified_join(workspace: Workspace, db: Database, artifact: dict[str, Any]) -> str | None:
    """Record a join as verified only after proving it against real data."""

    left, right = str(artifact.get("left") or ""), str(artifact.get("right") or "")
    if not left.count(".") == 1 or not right.count(".") == 1:
        return None
    left_table, left_column = left.split(".")
    right_table, right_column = right.split(".")
    try:
        from psycopg import sql as pgsql

        import psycopg

        query = pgsql.SQL("SELECT 1 FROM {lt} JOIN {rt} ON {lt}.{lc} = {rt}.{rc} LIMIT 1").format(
            lt=pgsql.Identifier(left_table),
            rt=pgsql.Identifier(right_table),
            lc=pgsql.Identifier(left_column),
            rc=pgsql.Identifier(right_column),
        )
        with db._limited(), psycopg.connect(db.dsn) as conn:
            if conn.execute(query).fetchone() is None:
                return None
    except Exception:
        return None
    path = "relationships/verified_joins.yaml"
    data = workspace.read_yaml(path, default={"joins": []}) or {"joins": []}
    joins = data.setdefault("joins", [])
    if any({item.get("left"), item.get("right")} == {left, right} for item in joins):
        return None
    joins.append({"left": left, "right": right, "cardinality": "unknown", "verified": True, "verified_by": "explorer"})
    workspace.write_yaml(path, data)
    return path


def _apply_dangerous_join(workspace: Workspace, artifact: dict[str, Any]) -> str | None:
    left, right = str(artifact.get("left") or ""), str(artifact.get("right") or "")
    if not left or not right:
        return None
    path = "relationships/dangerous_joins.yaml"
    data = workspace.read_yaml(path, default={"joins": []}) or {"joins": []}
    joins = data.setdefault("joins", [])
    if any(item.get("left") == left and item.get("right") == right for item in joins):
        return None
    joins.append(
        {
            "left": left,
            "right": right,
            "reason": str(artifact.get("reason") or "fanout discovered during exploration"),
            "required_action": str(artifact.get("required_action") or "preaggregate before joining"),
        }
    )
    workspace.write_yaml(path, data)
    return path


def _apply_rule(workspace: Workspace, artifact: dict[str, Any]) -> str | None:
    rule = str(artifact.get("rule") or "").strip()
    if not rule:
        return None
    path = "relationships/learned_rules.yaml"
    data = workspace.read_yaml(path, default={"rules": []}) or {"rules": []}
    rules = data.setdefault("rules", [])
    if any(item.get("rule") == rule for item in rules):
        return None
    rules.append({"rule": rule, "source": "explorer", "confidence": float(artifact.get("confidence") or 0.7)})
    workspace.write_yaml(path, data)
    return path


def reflect_node(state: ExplorerState, *, workspace: Workspace, db: Database, llm: OllamaClient | None) -> dict[str, Any]:
    written = list(state.get("written", []))
    successful = [item for item in state.get("results", []) if item.get("status") == "ok"]
    if not successful or llm is None:
        return {"written": written}
    brief_results = [
        {
            "name": item["name"],
            "question": item.get("question"),
            "sql": item["sql"],
            "columns": item.get("columns"),
            "sample_rows": item.get("sample_rows"),
            "rows": item.get("rows"),
        }
        for item in successful
    ]
    try:
        answer = llm.chat_json(
            "You just probed a PostgreSQL database. Decide which findings are reusable and safe to keep "
            "in your skill workspace. Only generalize from the actual probe results. "
            'Return JSON {"artifacts": [...]} where each artifact is one of: '
            '{"type": "template", "name", "description", "grain", "sql"} — reusable metric query based on '
            "a successful probe; "
            '{"type": "verified_join", "left": "table.column", "right": "table.column"} — a join that a '
            "successful probe actually used and that returned matching rows; "
            '{"type": "dangerous_join", "left", "right", "reason", "required_action"} — confirmed fanout; '
            '{"type": "rule", "rule"} — short reusable SQL rule for this database. '
            "Return an empty list when nothing is worth keeping.",
            json.dumps({"results": brief_results}, ensure_ascii=False, default=str),
        )
    except LLMUnavailable:
        return {"written": written}
    appliers = {"dangerous_join": _apply_dangerous_join, "rule": _apply_rule}
    for artifact in answer.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        if str(artifact.get("type")) == "template":
            changed = _apply_template(workspace, db, artifact)
        elif str(artifact.get("type")) == "verified_join":
            changed = _apply_verified_join(workspace, db, artifact)
        else:
            applier = appliers.get(str(artifact.get("type")))
            if applier is None:
                continue
            changed = applier(workspace, artifact)
        if changed:
            written.append(changed)
    return {"written": written}


SKILL_LESSONS_SECTION = "## Lessons from exploration"


def _update_skill_lessons(workspace: Workspace) -> None:
    """Rewrite the lessons section of SKILL.md from the reflection log (bounded, deduped)."""

    lessons = []
    for item in read_trajectories(_reflections_log_path(workspace)):
        for lesson in item.get("lessons", []):
            if lesson not in lessons:
                lessons.append(lesson)
    lessons = lessons[-8:]
    if not lessons:
        return
    skill_path = workspace.root / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else f"# {workspace.root.name} skill\n"
    head = content.split(SKILL_LESSONS_SECTION, 1)[0].rstrip()
    section = SKILL_LESSONS_SECTION + "\n" + "".join(f"- {lesson}\n" for lesson in lessons)
    workspace.write_text("SKILL.md", head + "\n\n" + section)


def self_reflect_node(state: ExplorerState, *, workspace: Workspace, llm: OllamaClient | None) -> dict[str, Any]:
    """The agent reviews its own round — successes, failures, repairs — and distills lessons."""

    results = state.get("results", [])
    if llm is None or not results:
        return {}
    ok = sum(1 for item in results if item.get("status") == "ok")
    repaired = sum(1 for item in results if item.get("repaired"))
    errors = [str(item.get("error", ""))[:150] for item in results if item.get("status") == "error"][:5]
    try:
        answer = llm.chat_json(
            "You just finished a self-exploration round on a PostgreSQL database. Reflect on your own work: "
            "which probes succeeded, which failed and why, and what your repairs teach you. Distill at most 3 "
            "concrete rules you will follow in the next rounds (identifier habits, join discipline, query "
            "shapes). Do not repeat your earlier lessons. "
            'Return JSON {"lessons": ["..."], "note": "one sentence summary"}.',
            json.dumps(
                {
                    "round": state.get("round_index", 0),
                    "probes_ok": ok,
                    "probes_failed": len(results) - ok,
                    "repaired_by_error_feedback": repaired,
                    "corrections_learned": state.get("corrections", []),
                    "errors": errors,
                    "earlier_lessons": _recent_lessons(workspace),
                },
                ensure_ascii=False,
                default=str,
            ),
        )
    except LLMUnavailable:
        return {}
    lessons = [str(lesson).strip()[:300] for lesson in answer.get("lessons") or [] if str(lesson).strip()][:3]
    if not lessons:
        return {}
    append_trajectory(
        _reflections_log_path(workspace),
        {
            "round": state.get("round_index", 0),
            "stats": {"ok": ok, "failed": len(results) - ok, "repaired": repaired},
            "lessons": lessons,
            "note": str(answer.get("note", ""))[:300],
        },
    )
    _update_skill_lessons(workspace)
    return {}


def run_exploration(
    db: Database,
    workspace: Workspace,
    llm: OllamaClient | None = None,
    rounds: int = 3,
    probes_per_round: int = 3,
    domain: str | None = None,
) -> dict[str, Any]:
    """Run bounded plan -> act -> reflect -> self-reflect rounds; each round ends with a git commit."""

    workspace.ensure_git()

    def plan(state: ExplorerState) -> dict[str, Any]:
        return plan_node(state, workspace=workspace, llm=llm)

    def act(state: ExplorerState) -> dict[str, Any]:
        return act_node(state, db=db, workspace=workspace, llm=llm)

    def reflect(state: ExplorerState) -> dict[str, Any]:
        return reflect_node(state, workspace=workspace, db=db, llm=llm)

    def self_reflect(state: ExplorerState) -> dict[str, Any]:
        return self_reflect_node(state, workspace=workspace, llm=llm)

    def commit(state: ExplorerState) -> dict[str, Any]:
        round_index = state.get("round_index", 0)
        workspace.commit(f"explore: round {round_index}")
        return {"round_index": round_index + 1}

    def route_after_plan(state: ExplorerState) -> str:
        return "act" if state.get("probes") else "finish"

    def route_after_commit(state: ExplorerState) -> str:
        if state.get("stop_reason"):
            return "finish"
        return "plan" if state.get("round_index", 0) < state.get("rounds", rounds) else "finish"

    graph = StateGraph(ExplorerState)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("reflect", reflect)
    graph.add_node("self_reflect", self_reflect)
    graph.add_node("commit", commit)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {"act": "act", "finish": END})
    graph.add_edge("act", "reflect")
    graph.add_edge("reflect", "self_reflect")
    graph.add_edge("self_reflect", "commit")
    graph.add_conditional_edges("commit", route_after_commit, {"plan": "plan", "finish": END})
    result = graph.compile().invoke(
        {
            "workspace_path": str(workspace.root),
            "rounds": max(1, rounds),
            "probes_per_round": max(1, probes_per_round),
            "round_index": 0,
            "written": [],
            "domain": domain or "",
        }
    )
    return {
        "workspace": str(workspace.root),
        "domain": domain or None,
        "rounds_run": result.get("round_index", 0),
        "written": result.get("written", []),
        "stop_reason": result.get("stop_reason"),
    }


def optimize_skill(
    db: Database,
    workspace: Workspace,
    llm: OllamaClient | None = None,
    *,
    rounds_per_domain: int = 1,
    probes_per_round: int = 3,
) -> dict[str, Any]:
    """Improve each sub-skill separately: one focused exploration round per domain,
    with the schema scoped to that domain's tables, then a final verification pass."""

    from sqlagent.verification import verify_skill

    manifest = workspace.read_manifest()
    domains = sorted((manifest.get("domains") or {}).keys())
    per_domain: dict[str, Any] = {}
    targets = domains or [None]
    for domain in targets:
        per_domain[domain or "all"] = run_exploration(
            db,
            workspace,
            llm,
            rounds=rounds_per_domain,
            probes_per_round=probes_per_round,
            domain=domain,
        )
    verification = verify_skill(db, workspace)
    written = sum(len(result.get("written", [])) for result in per_domain.values())
    return {
        "status": f"{written} artifacts across {len(per_domain)} domains, {len(verification['failing'])} failing templates",
        "domains": per_domain,
        "verification": {"checked": verification["checked"], "failing": verification["failing"]},
    }
