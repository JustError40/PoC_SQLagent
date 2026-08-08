from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypedDict

import psycopg
from langgraph.graph import END, START, StateGraph
from psycopg import sql

from sqlagent.db import Database, json_safe
from sqlagent.llm import LLMUnavailable, OllamaClient
from sqlagent.workspace import Workspace


class SurveyState(TypedDict, total=False):
    inventory: list[dict[str, Any]]
    columns: dict[str, list[dict[str, Any]]]
    constraints: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    profiles: dict[str, dict[str, Any]]
    primary_keys: dict[str, list[str]]
    verified_joins: list[dict[str, Any]]
    dangerous_joins: list[dict[str, Any]]
    semantics: dict[str, dict[str, str]]
    domains: dict[str, list[str]]
    workspace_path: str
    llm_used: bool


FANOUT_THRESHOLD = 1.2


def _fetch_rows(conn: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(query, params) if params else conn.execute(query)
    columns = [description.name for description in cursor.description or []]
    return [json_safe(dict(zip(columns, row))) for row in cursor.fetchall()]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "domain"


def inventory_node(state: SurveyState, *, db: Database) -> dict[str, Any]:
    with db._limited(), psycopg.connect(db.dsn) as conn:
        tables = _fetch_rows(
            conn,
            """
            SELECT table_name, table_type
            FROM information_schema.tables t
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
              AND NOT EXISTS (
                  SELECT 1
                  FROM pg_inherits i
                  JOIN pg_class c ON c.oid = i.inhrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relname = t.table_name
              )
            ORDER BY table_name
            """,
        )
        columns: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            columns[table["table_name"]] = _fetch_rows(
                conn,
                """
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table["table_name"],),
            )
        constraints = _fetch_rows(
            conn,
            """
            SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
                   kcu.column_name, ccu.table_name AS foreign_table_name,
                   ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            LEFT JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            WHERE tc.table_schema = 'public'
            ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
            """,
        )
        indexes = _fetch_rows(
            conn,
            """
            SELECT tablename AS table_name, indexname AS index_name, indexdef
            FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname
            """,
        )
    primary_keys: dict[str, list[str]] = {}
    for row in constraints:
        if row["constraint_type"] == "PRIMARY KEY" and row.get("column_name"):
            primary_keys.setdefault(row["table_name"], []).append(row["column_name"])
    return {
        "inventory": tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "primary_keys": primary_keys,
    }


def profiling_node(state: SurveyState, *, db: Database) -> dict[str, Any]:
    def profile_table(item: tuple[str, list[dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
        table, columns = item
        with db._limited(), psycopg.connect(db.dsn) as conn:
            table_ident = sql.Identifier(table)
            table_profile: dict[str, Any] = {}
            for column in columns:
                name = column["column_name"]
                ident = sql.Identifier(name)
                query = sql.SQL(
                    "SELECT count(*) AS total, count({col}) AS non_null, "
                    "count(DISTINCT {col}) AS distinct_count, "
                    "min({col})::text AS min_value, max({col})::text AS max_value "
                    "FROM {table}"
                ).format(col=ident, table=table_ident)
                try:
                    row = conn.execute(query).fetchone()
                    total, non_null, distinct_count, min_value, max_value = row
                    table_profile[name] = {
                        "total": int(total),
                        "nulls": int(total - non_null),
                        "distinct": int(distinct_count),
                        "min": min_value,
                        "max": max_value,
                    }
                    if column["data_type"] in {"text", "character varying"} and distinct_count <= 50:
                        top_query = sql.SQL(
                            "SELECT {col}::text AS value, count(*) AS n FROM {table} "
                            "WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY n DESC, value LIMIT 50"
                        ).format(col=ident, table=table_ident)
                        table_profile[name]["top_values"] = [
                            {"value": value, "count": int(n)} for value, n in conn.execute(top_query).fetchall()
                        ]
                except psycopg.Error:
                    table_profile[name] = {"error": "profile query failed"}
        return table, table_profile

    items = list(state["columns"].items())
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(items))), thread_name_prefix="survey-profile") as pool:
        profiles = dict(pool.map(profile_table, items))
    return {"profiles": profiles}


def joins_node(state: SurveyState, *, db: Database) -> dict[str, Any]:
    """Verify FK-derived join candidates against real data and classify fanout risk."""

    foreign_keys = [
        row
        for row in state["constraints"]
        if row["constraint_type"] == "FOREIGN KEY" and row.get("foreign_table_name") and row.get("column_name")
    ]
    known_tables = set(state["columns"])
    def verify_fk(fk: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with db._limited(), psycopg.connect(db.dsn) as conn:
            child, column = fk["table_name"], fk["column_name"]
            parent, parent_column = fk["foreign_table_name"], fk["foreign_column_name"]
            if child not in known_tables or parent not in known_tables:
                return None, None
            query = sql.SQL(
                "SELECT count(*) AS total, count({col}) AS non_null, "
                "count(DISTINCT {col}) AS distinct_refs FROM {table}"
            ).format(col=sql.Identifier(column), table=sql.Identifier(child))
            try:
                total, non_null, distinct_refs = conn.execute(query).fetchone()
            except psycopg.Error:
                return None, None
            fanout = round(non_null / distinct_refs, 3) if distinct_refs else 0.0
            null_fraction = round((total - non_null) / total, 3) if total else 0.0
            cardinality = "one_to_one_expected" if 0 < fanout <= 1.05 else "many_to_one"
            verified = {
                "left": f"{child}.{column}",
                "right": f"{parent}.{parent_column}",
                "cardinality": cardinality,
                "verified": True,
                "avg_fanout": fanout,
                "null_fraction": null_fraction,
            }
            dangerous = None
            if fanout > FANOUT_THRESHOLD:
                dangerous = {
                    "left": f"{parent}.{parent_column}",
                    "right": f"{child}.{column}",
                    "reason": f"one-to-many fanout: avg {fanout} {child} rows per {parent} row",
                    "required_action": f"preaggregate {child} before joining {parent}-grain measures",
                }
            return verified, dangerous

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(foreign_keys))), thread_name_prefix="survey-join") as pool:
        checked = list(pool.map(verify_fk, foreign_keys))
    verified = [item[0] for item in checked if item[0] is not None]
    dangerous = [item[1] for item in checked if item[1] is not None]
    return {"verified_joins": verified, "dangerous_joins": dangerous}


def _profile_hints(state: SurveyState, table: str) -> dict[str, Any]:
    """Compact per-column hints (samples/ranges) to ground LLM semantics in data."""

    hints: dict[str, Any] = {}
    for column, profile in (state.get("profiles", {}).get(table) or {}).items():
        if "error" in profile:
            continue
        hint: dict[str, Any] = {}
        if profile.get("top_values"):
            hint["sample_values"] = [item["value"] for item in profile["top_values"][:5]]
        if profile.get("min") is not None and profile.get("max") is not None:
            hint["range"] = [str(profile["min"])[:40], str(profile["max"])[:40]]
        hint["distinct"] = profile.get("distinct")
        hints[column] = hint
    return hints


def semantics_node(state: SurveyState, *, llm: OllamaClient | None = None) -> dict[str, Any]:
    semantics = {
        table: {
            "description": f"Table {table} with {len(columns)} columns.",
            "grain": "one row per " + ", ".join(state.get("primary_keys", {}).get(table) or ["record"]),
        }
        for table, columns in state["columns"].items()
    }
    used = False
    if llm:
        def describe(item: tuple[str, list[dict[str, Any]]]) -> tuple[str, dict[str, Any] | None]:
            table, columns = item
            brief = {
                table: {
                    "columns": [f"{column['column_name']} {column['data_type']}" for column in columns][:40],
                    "hints": _profile_hints(state, table),
                }
            }
            try:
                answer = llm.chat_json(
                    "You document a PostgreSQL database for a SQL agent. For each table return a concise "
                    "description (one sentence, grounded in column names and sample values) and its grain "
                    "('one row per ...'). Return JSON object table -> {description, grain}. "
                    "Do not invent business facts that the columns do not support.",
                    json.dumps(brief, ensure_ascii=False),
                )
            except LLMUnavailable:
                return table, None
            value = answer.get(table) if isinstance(answer, dict) else None
            return table, value if isinstance(value, dict) else None

        items = list(state["columns"].items())
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(items))), thread_name_prefix="survey-semantics") as pool:
            descriptions = list(pool.map(describe, items))
        for table, value in descriptions:
            if value is not None:
                semantics[table].update(
                    {key: str(val) for key, val in value.items() if key in {"description", "grain"}}
                )
                used = True
    return {"semantics": semantics, "llm_used": used}


def domains_node(state: SurveyState, *, llm: OllamaClient | None = None) -> dict[str, Any]:
    known = sorted(state["columns"])
    domains: dict[str, list[str]] = {"all": known}
    if llm:
        brief = {
            table: {
                "description": state["semantics"][table]["description"],
                "columns": [column["column_name"] for column in state["columns"][table]][:30],
            }
            for table in known
        }
        try:
            answer = llm.chat_json(
                "Group these database tables into 2-6 coherent business domains. "
                "Return JSON object domain_name -> [table names]. Every table must appear in exactly one domain. "
                "Use short lowercase snake_case domain names.",
                json.dumps(brief, ensure_ascii=False),
            )
            grouped: dict[str, list[str]] = {}
            assigned: set[str] = set()
            for name, tables in answer.items():
                if not isinstance(tables, list):
                    continue
                members = [str(table) for table in tables if str(table) in known and str(table) not in assigned]
                if members:
                    grouped[_slug(str(name))] = sorted(members)
                    assigned.update(members)
            missing = sorted(set(known) - assigned)
            if missing:
                grouped["other"] = missing
            if grouped:
                domains = grouped
        except LLMUnavailable:
            pass
    return {"domains": domains}


def _skill_md(workspace_name: str, dangerous_joins: list[dict[str, Any]]) -> str:
    lines = [
        f"# {workspace_name} skill",
        "",
        "## Router",
        "Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.",
        "",
        "## Query protocol",
        "1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.",
        "4. Run EXPLAIN before execution. 5. Check invariants before returning results.",
        "",
        "## Grain rules",
    ]
    if dangerous_joins:
        for join in dangerous_joins:
            lines.append(f"- `{join['left']}` -> `{join['right']}`: {join['reason']}; {join['required_action']}.")
    else:
        lines.append("- No one-to-many fanout joins detected during survey.")
    return "\n".join(lines) + "\n"


def save_node(state: SurveyState) -> dict[str, Any]:
    workspace = Workspace(Path(state["workspace_path"]))
    workspace.ensure_git()
    workspace.write_text(".gitignore", "experience/trajectories.jsonl\n.cache/\n")
    if workspace._git("ls-files", "--error-unmatch", "experience/trajectories.jsonl", check=False):
        workspace._git("rm", "--cached", "--ignore-unmatch", "experience/trajectories.jsonl")
    workspace.write_text("SKILL.md", _skill_md(workspace.root.name, state["dangerous_joins"]))
    manifest = {
        "version": 1,
        "workspace": workspace.root.name,
        "generated_by": "surveyor",
        "tables": sorted(state["columns"]),
        "domains": state["domains"],
        "artifacts": {
            "schema": "schema/tables.yaml",
            "relationships": "relationships/verified_joins.yaml",
            "dangerous_joins": "relationships/dangerous_joins.yaml",
            "policies": "policies/forbidden_operations.yaml",
            "invariants": "evals/invariants.yaml",
            "templates": "templates/",
        },
        # name -> {path, description, grain}; the explorer and evolution fill this in.
        "templates": {},
    }
    workspace.write_yaml("manifest.yaml", manifest)
    workspace.write_yaml(
        "schema/tables.yaml",
        {
            "tables": [
                {
                    "name": table,
                    "description": state["semantics"][table]["description"],
                    "grain": state["semantics"][table]["grain"],
                    "columns": columns,
                }
                for table, columns in state["columns"].items()
            ]
        },
    )
    workspace.write_yaml(
        "schema/constraints.yaml",
        {"constraints": state["constraints"], "indexes": state["indexes"]},
    )
    workspace.write_json("raw/schema_snapshot.json", {"tables": state["inventory"], "columns": state["columns"], "constraints": state["constraints"], "indexes": state["indexes"]})
    workspace.write_json("raw/profile_snapshot.json", state["profiles"])
    workspace.write_yaml("profiles/columns.yaml", state["profiles"])
    workspace.write_yaml("domains/index.yaml", state["domains"])
    for domain, tables in state["domains"].items():
        workspace.write_yaml(f"domains/{domain}.yaml", {"domain": domain, "tables": tables})
    workspace.write_yaml("relationships/verified_joins.yaml", {"joins": state["verified_joins"]})
    workspace.write_yaml("relationships/dangerous_joins.yaml", {"joins": state["dangerous_joins"]})
    workspace.write_yaml("policies/forbidden_operations.yaml", {"read_only": True, "forbidden_tables": ["pg_authid", "pg_shadow"], "max_result_rows": 500, "explain_required": True})
    invariants = [{"id": "bounded_result", "expression": "rows <= 500"}]
    for index, join in enumerate(state["dangerous_joins"]):
        invariants.append({"id": f"no_fanout_{index}", "expression": join["required_action"]})
    workspace.write_yaml("evals/invariants.yaml", {"invariants": invariants})
    workspace.write_text("experience/exploration.jsonl", "")
    workspace.write_text("experience/trajectories.jsonl", "")
    workspace.commit("survey: generate skill workspace")
    return {"workspace": str(workspace.root), "tables": len(state["columns"]), "llm_used": state.get("llm_used", False)}


def run_survey(db: Database, workspace: Workspace, llm: OllamaClient | None = None) -> dict[str, Any]:
    """Run the inventory -> profiling -> joins -> semantics -> domains -> save graph."""

    def inventory(state: SurveyState) -> dict[str, Any]:
        return inventory_node(state, db=db)

    def profiling(state: SurveyState) -> dict[str, Any]:
        return profiling_node(state, db=db)

    def joins(state: SurveyState) -> dict[str, Any]:
        return joins_node(state, db=db)

    def semantics(state: SurveyState) -> dict[str, Any]:
        return semantics_node(state, llm=llm)

    def domains(state: SurveyState) -> dict[str, Any]:
        return domains_node(state, llm=llm)

    def save(state: SurveyState) -> dict[str, Any]:
        return save_node(state)

    graph = StateGraph(SurveyState)
    graph.add_node("inventory", inventory)
    graph.add_node("profiling", profiling)
    graph.add_node("joins", joins)
    graph.add_node("semantics", semantics)
    graph.add_node("domains", domains)
    graph.add_node("save", save)
    graph.add_edge(START, "inventory")
    graph.add_edge("inventory", "profiling")
    graph.add_edge("profiling", "joins")
    graph.add_edge("joins", "semantics")
    graph.add_edge("semantics", "domains")
    graph.add_edge("domains", "save")
    graph.add_edge("save", END)
    result = graph.compile().invoke({"workspace_path": str(workspace.root)})
    return {"workspace": str(workspace.root), "tables": len(result.get("columns", {})), "llm_used": result.get("llm_used", False)}
