from __future__ import annotations

import hashlib
import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from sqlagent.composer import DECOMPOSE_PROMPT, SPEC_JSON_SCHEMA, assemble_spec
from sqlagent.db import Database, QueryResult, QuerySafetyError
from sqlagent.llm import LLMUnavailable, OllamaClient
from sqlagent.sqllint import lint_sql, schema_from_tables_yaml
from sqlagent.trajectories import append_trajectory
from sqlagent.workspace import Workspace


def _workspace_schema(workspace: Workspace) -> dict[str, list[str]]:
    tables = (workspace.read_yaml("schema/tables.yaml", default={}) or {}).get("tables", [])
    return schema_from_tables_yaml(tables)


class QueryState(TypedDict, total=False):
    question: str
    workspace_path: str
    selected_files: list[str]
    loaded_files: dict[str, str]
    route: str
    template: str
    plan: str
    sql: str
    explain: dict[str, Any]
    result: dict[str, Any]
    invariants: dict[str, Any]
    error: str
    llm_used: bool
    telemetry: dict[str, Any]
    clarification: str
    react_attempts: int
    react_steps: list[dict[str, Any]]
    react_repair_ready: bool
    react_retry: bool
    spec: dict[str, Any]
    schema_scope: list[str]
    critic: dict[str, Any]
    critic_rejected: bool


CORE_FILES = [
    "SKILL.md",
    "manifest.yaml",
    "schema/tables.yaml",
    "schema/identifier_notes.yaml",
    "relationships/verified_joins.yaml",
    "relationships/dangerous_joins.yaml",
    "evals/invariants.yaml",
]

_AMBIGUITY_TERMS = (
    "как дела",
    "показател",
    "эффектив",
    "успеш",
    "результат",
    "ситуац",
    "performance",
    "overall",
)
REACT_MAX_ATTEMPTS = 3

_META_QUESTION_TERMS = ("таблиц", "колонк", "table", "column", "schema", "схема", "каталог")
_SYSTEM_CATALOG_RE = re.compile(r"\b(information_schema|pg_catalog)\b", re.IGNORECASE)


def metadata_drift(question: str, sql: str) -> bool:
    """The query reads catalog metadata while the question asks about business data."""

    if not _SYSTEM_CATALOG_RE.search(sql):
        return False
    normalized = question.lower()
    return not any(term in normalized for term in _META_QUESTION_TERMS)


def detect_ambiguity(question: str, known_metrics: list[str] | None = None) -> dict[str, Any]:
    """Return a stable, model-independent ambiguity telemetry payload."""

    normalized = question.lower()
    metrics = list(known_metrics or [])
    explicit_metrics = [metric for metric in metrics if any(part in normalized for part in metric.lower().split("_") if len(part) > 3)]
    ambiguous = any(term in normalized for term in _AMBIGUITY_TERMS)
    if not explicit_metrics and any(term in normalized for term in ("что важнее", "что показать", "главн")):
        ambiguous = True
    return {
        "ambiguity_detected": ambiguous,
        "possible_metrics": metrics if ambiguous else explicit_metrics,
        "clarification_requested": ambiguous,
    }


def clarification_prompt(telemetry: dict[str, Any]) -> str:
    metrics = telemetry.get("possible_metrics") or []
    suffix = ", ".join(metrics) if metrics else "уточните метрику"
    return f"Уточните, какую метрику посчитать: {suffix}."


def route_question(
    question: str,
    *,
    manifest: dict[str, Any],
    llm: OllamaClient | None = None,
) -> tuple[str, list[str], str | None]:
    """Pick a domain, skill files and an optional template using the manifest and, when
    available, the LLM. Falls back to the generic core file set without an LLM."""

    domains = manifest.get("domains") or {}
    # Templates that failed periodic revalidation are no longer trusted; the agent
    # falls back to another template or to fresh generation instead of using them.
    raw_templates = manifest.get("templates") or {}
    if not isinstance(raw_templates, dict):  # legacy manifest shape
        raw_templates = {}
    templates = {
        name: meta
        for name, meta in raw_templates.items()
        if str((meta or {}).get("status") or "ok") != "failing"
    }
    files = list(CORE_FILES)
    route = ""
    template: str | None = None
    if llm and domains:
        brief = {
            "question": question,
            "domains": {name: tables for name, tables in domains.items()},
            "templates": {
                name: {
                    "description": (meta or {}).get("description", ""),
                    "avg_elapsed_ms": ((meta or {}).get("metrics") or {}).get("avg_elapsed_ms"),
                }
                for name, meta in templates.items()
            },
        }
        try:
            answer = llm.chat_json(
                "You route a natural-language question to skill workspace files. Pick the single most "
                "relevant domain and, when one clearly matches the question, a template. When several "
                "templates match equally, prefer the one with the lower avg_elapsed_ms. Return JSON "
                '{"domain": name or null, "template": name or null}. Use only names from the provided lists.',
                json.dumps(brief, ensure_ascii=False),
            )
            domain = str(answer.get("domain") or "")
            if domain in domains:
                route = domain
            candidate = str(answer.get("template") or "")
            if candidate in templates:
                template = candidate
        except LLMUnavailable:
            pass
    if route and route in domains:
        files.append(f"domains/{route}.yaml")
    else:
        files.append("domains/index.yaml")
    if template:
        path = str((templates.get(template) or {}).get("path") or "")
        if path:
            files.append(path)
    return route, files, template


def _clean_sql(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:sql)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            value = str(parsed.get("sql", value))
        except json.JSONDecodeError:
            pass
    # Models sometimes prepend prose or notation garbage; keep only the first statement.
    match = None if value.lower().startswith("with") else (
        re.search(r"\bselect\b", value, re.IGNORECASE) or re.search(r"\bwith\b", value, re.IGNORECASE)
    )
    if match:
        value = value[match.start() :]
    if ";" in value:
        value = value[: value.index(";") + 1]
    return value.strip()


def _invariant_check(result: QueryResult, declared: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Generic checks plus machine-checkable invariants declared by the skill itself.

    The agent code makes no assumptions about measure names; per-database rules such as
    {"type": "non_negative", "column": "revenue"} are learned into evals/invariants.yaml.
    """

    failures: list[str] = []
    for invariant in declared or []:
        if not isinstance(invariant, dict) or invariant.get("type") != "non_negative":
            continue
        column = str(invariant.get("column") or "").lower()
        if not column:
            continue
        for row in result.rows:
            value = row.get(column)
            if isinstance(value, (int, float)) and value < 0:
                failures.append(f"{invariant.get('id', column)}: {column} is negative")
    return {"passed": not failures and len(result.rows) <= 500, "failures": failures, "rows": len(result.rows)}


def _record_template_metrics(workspace: Workspace, state: "QueryState") -> None:
    """Accumulate per-template efficiency stats so the router can prefer fast templates."""

    template = state.get("template")
    result = state.get("result") or {}
    elapsed = result.get("elapsed_ms")
    if not template or state.get("error") or not isinstance(elapsed, (int, float)):
        return
    manifest = workspace.read_yaml("manifest.yaml", default={}) or {}
    templates = manifest.get("templates")
    if not isinstance(templates, dict) or template not in templates:
        return
    entry = dict(templates[template] or {})
    metrics = dict(entry.get("metrics") or {})
    uses = int(metrics.get("uses") or 0)
    avg = float(metrics.get("avg_elapsed_ms") or 0.0)
    metrics["uses"] = uses + 1
    metrics["avg_elapsed_ms"] = round((avg * uses + float(elapsed)) / (uses + 1), 3)
    metrics["last_rows"] = len(result.get("rows") or [])
    entry["metrics"] = metrics
    templates[template] = entry
    manifest["templates"] = templates
    workspace.write_yaml("manifest.yaml", manifest)


def _learn_template(workspace: Workspace, state: "QueryState") -> None:
    """Promote a successful model-built query into the skill as a learned template.

    Only queries that executed cleanly and passed the critic are kept, so the
    skill grows from verified answers. Efficiency metrics accumulate on reuse,
    and periodic verification re-validates them like any other template.
    """

    if state.get("error") or state.get("template") or not state.get("llm_used"):
        return
    critic = state.get("critic")
    if critic and not critic.get("answered", True):
        return
    sql_text = (state.get("sql") or "").strip()
    if not sql_text:
        return
    try:
        fingerprint = hashlib.sha1(sql_text.encode("utf-8")).hexdigest()[:10]
        manifest = workspace.read_yaml("manifest.yaml", default={}) or {}
        templates = manifest.get("templates")
        if not isinstance(templates, dict):
            templates = {}
        if any(str((meta or {}).get("fingerprint")) == fingerprint for meta in templates.values()):
            return
        name = f"learned_{fingerprint}"
        path = f"templates/{name}.sql"
        spec = state.get("spec") or {}
        grain = ", ".join(
            str(dim.get("column")) for dim in spec.get("group_by", []) if isinstance(dim, dict) and dim.get("column")
        )
        workspace.write_text(path, sql_text + ";\n")
        templates[name] = {
            "path": path,
            "description": state["question"][:200],
            "grain": grain,
            "fingerprint": fingerprint,
            "source": "query_agent",
            "spec": spec or None,
            "explain_cost": (state.get("explain") or {}).get("total_cost"),
            "status": "ok",
        }
        manifest["templates"] = templates
        workspace.write_yaml("manifest.yaml", manifest)
        workspace.ensure_git()
        workspace.commit(f"learn: template {name}")
    except Exception:
        pass  # learning must never break answering


def _schema_digest(loaded_files: dict[str, str], only_tables: set[str] | None = None) -> dict[str, list[str]]:
    """Compact {table: [columns]} map — small models ground on this far better
    than on full YAML dumps, so they stop inventing identifiers."""

    import yaml

    raw = loaded_files.get("schema/tables.yaml")
    if not raw:
        return {}
    try:
        tables = (yaml.safe_load(raw) or {}).get("tables", [])
    except yaml.YAMLError:
        return {}
    return {
        str(table["name"]): [str(c["column_name"]) for c in table.get("columns", []) if c.get("column_name")]
        for table in tables
        if isinstance(table, dict) and table.get("name") and (only_tables is None or str(table["name"]) in only_tables)
    }


def _domain_tables(loaded_files: dict[str, str], route: str) -> set[str] | None:
    """Tables of the routed domain, so generation happens over a small relevant schema."""

    import yaml

    if not route:
        return None
    raw = loaded_files.get(f"domains/{route}.yaml")
    if not raw:
        return None
    try:
        tables = (yaml.safe_load(raw) or {}).get("tables", [])
    except yaml.YAMLError:
        return None
    tables = [str(table) for table in tables if table]
    return set(tables) or None


def _generation_context(state: "QueryState", only_tables: set[str] | None = None) -> dict[str, Any]:
    loaded = state.get("loaded_files", {})
    if only_tables is None:
        only_tables = _domain_tables(loaded, state.get("route", ""))
    examples = {
        path.rsplit("/", 1)[-1].removesuffix(".sql"): content.strip()[:600]
        for path, content in loaded.items()
        if path.startswith("templates/") and content.strip()
    }
    return {
        "question": state["question"],
        "schema": _schema_digest(loaded, only_tables),
        "verified_joins": loaded.get("relationships/verified_joins.yaml", "")[:1200],
        "dangerous_joins": loaded.get("relationships/dangerous_joins.yaml", "")[:800],
        "identifier_notes": loaded.get("schema/identifier_notes.yaml", "")[:800],
        "example_queries": examples,
    }


def _table_descriptions(loaded_files: dict[str, str]) -> dict[str, str]:
    import yaml

    raw = loaded_files.get("schema/tables.yaml")
    if not raw:
        return {}
    try:
        tables = (yaml.safe_load(raw) or {}).get("tables", [])
    except yaml.YAMLError:
        return {}
    return {
        str(table["name"]): str(table.get("description") or "")
        for table in tables
        if isinstance(table, dict) and table.get("name")
    }


def _select_tables(state: "QueryState", schema_map: dict[str, list[str]], llm: "OllamaClient") -> set[str] | None:
    """Table-selector subagent: a tiny multiple-choice task that even a small model
    can do — pick the few tables a question needs before planning the query."""

    if len(schema_map) <= 4:
        return None
    loaded = state.get("loaded_files", {})
    descriptions = _table_descriptions(loaded)
    # Column names carry the real semantics (descriptions may be generic), so the
    # selector sees both table names and a sample of their columns.
    brief = {
        name: {"about": descriptions.get(name, "")[:100], "columns": columns[:12]}
        for name, columns in schema_map.items()
    }
    try:
        answer = llm.chat_json(
            "You choose which database tables are needed to answer a question. Pick 1 to 3 tables, "
            "only from the provided list. Return JSON {\"tables\": [names]}.",
            json.dumps({"question": state["question"], "tables": brief}, ensure_ascii=False),
        )
    except LLMUnavailable:
        return None
    if not isinstance(answer, dict):
        return None
    chosen = {str(table) for table in answer.get("tables") or [] if str(table) in schema_map}
    return chosen or None


class QueryAgent:
    def __init__(self, db: Database, workspace: Workspace, llm: OllamaClient | None = None) -> None:
        self.db = db
        self.workspace = workspace
        self.llm = llm

    def run(self, question: str) -> dict[str, Any]:
        graph = StateGraph(QueryState)

        def router(state: QueryState) -> dict[str, Any]:
            manifest = self.workspace.read_yaml("manifest.yaml", default={}) or {}
            route, files, template = route_question(state["question"], manifest=manifest, llm=self.llm)
            return {"route": route, "selected_files": files, "template": template or ""}

        def loader(state: QueryState) -> dict[str, Any]:
            loaded = {}
            for relative in state["selected_files"]:
                path = self.workspace.root / relative
                if path.exists():
                    loaded[relative] = path.read_text(encoding="utf-8")
            # A few verified templates serve as few-shot style examples for generation,
            # even when none of them directly matches the question. Templates that touch
            # the routed domain's tables come first.
            manifest = self.workspace.read_yaml("manifest.yaml", default={}) or {}
            templates = manifest.get("templates")
            if isinstance(templates, dict):
                domain_tables = _domain_tables(loaded, state.get("route", ""))
                candidates = []
                for meta in templates.values():
                    relative = str((meta or {}).get("path") or "")
                    if not relative or relative in loaded:
                        continue
                    path = self.workspace.root / relative
                    if not path.exists():
                        continue
                    content = path.read_text(encoding="utf-8")
                    score = 0
                    if domain_tables:
                        score = sum(1 for table in domain_tables if re.search(rf"\b{re.escape(table)}\b", content))
                    candidates.append((score, relative, content))
                candidates.sort(key=lambda item: -item[0])
                for _, relative, content in candidates[:3]:
                    loaded[relative] = content
            return {"loaded_files": loaded}

        def telemetry(state: QueryState) -> dict[str, Any]:
            manifest = self.workspace.read_yaml("manifest.yaml", default={}) or {}
            known_metrics = sorted((manifest.get("templates") or {}).keys())
            payload = detect_ambiguity(state["question"], known_metrics)
            return {
                "telemetry": payload,
                "clarification": clarification_prompt(payload) if payload["clarification_requested"] else "",
            }

        def planner(state: QueryState) -> dict[str, Any]:
            if state.get("telemetry", {}).get("clarification_requested"):
                return {"plan": "request metric clarification before generating SQL"}
            if state.get("template"):
                return {"plan": f"reuse template {state['template']} at its documented grain"}
            return {"plan": "select the smallest verified domain, identify grain, generate one read-only query"}

        def sql_generator(state: QueryState) -> dict[str, Any]:
            template = state.get("template")
            manifest = self.workspace.read_yaml("manifest.yaml", default={}) or {}
            if template:
                path = str(((manifest.get("templates") or {}).get(template) or {}).get("path") or "")
                if path and path in state["loaded_files"]:
                    return {"sql": _clean_sql(state["loaded_files"][path]), "llm_used": False}
            if self.llm:
                schema_map = _workspace_schema(self.workspace)
                if schema_map:
                    # Primary path: the model plans the query in small JSON parts and the
                    # deterministic assembler builds the SQL (no syntax hallucination).
                    scope = _domain_tables(state.get("loaded_files", {}), state.get("route", ""))
                    if scope is None:
                        scope = _select_tables(state, schema_map, self.llm)
                    context = _generation_context(state, scope)
                    scoped = {"schema_scope": sorted(scope)} if scope else {}
                    try:
                        spec = self.llm.chat_json(
                            DECOMPOSE_PROMPT,
                            json.dumps(context, ensure_ascii=False),
                            schema=SPEC_JSON_SCHEMA,
                        )
                    except LLMUnavailable as exc:
                        return {"error": f"SQL generation failed: {exc}", "llm_used": False}
                    if isinstance(spec, dict) and spec.get("needed_tables"):
                        # The decomposer asked to load more skill parts: expand the scope once,
                        # exactly like the main skill routes to sub-skills on demand.
                        requested = {str(table) for table in spec.get("needed_tables") or [] if str(table) in schema_map}
                        if requested and not requested <= (scope or set()):
                            scope = (scope or set()) | requested
                            scoped = {"schema_scope": sorted(scope)}
                            try:
                                spec = self.llm.chat_json(
                                    DECOMPOSE_PROMPT,
                                    json.dumps(_generation_context(state, scope), ensure_ascii=False),
                                    schema=SPEC_JSON_SCHEMA,
                                )
                            except LLMUnavailable as exc:
                                return {"error": f"SQL generation failed: {exc}", "llm_used": False}
                    if isinstance(spec, dict) and spec.get("from"):
                        try:
                            return {"sql": assemble_spec(spec, schema_map), "spec": spec, "llm_used": True, **scoped}
                        except ValueError as exc:
                            return {"spec": spec, "error": f"query plan assembly failed: {exc}", "llm_used": True, **scoped}
                # Fallback for providers that cannot emit a query plan: free-form SQL.
                try:
                    answer = self.llm.chat_json(
                        "You generate one PostgreSQL SELECT that answers the question. Use only the exact "
                        "tables and columns from the schema map — never invent identifiers. Respect table "
                        "grain and verified/dangerous joins. Return JSON {sql: string}.",
                        json.dumps(_generation_context(state), ensure_ascii=False),
                    )
                    return {"sql": _clean_sql(str(answer["sql"])), "llm_used": True}
                except (LLMUnavailable, KeyError, ValueError, TypeError) as exc:
                    return {"error": f"SQL generation failed: {exc}", "llm_used": False}
            return {"error": "No matching template in the skill manifest and no LLM available to generate SQL", "llm_used": False}

        def validator(state: QueryState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                from sqlagent.db import validate_read_only

                query = validate_read_only(state["sql"])
                lint_schema = _workspace_schema(self.workspace)
                if lint_schema:
                    problems = lint_sql(query, lint_schema)
                    if problems:
                        return {"error": "lint failed: " + "; ".join(problems)}
                return {"sql": query}
            except QuerySafetyError as exc:
                return {"error": str(exc)}

        def explainer(state: QueryState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                return {"explain": self.db.explain(state["sql"])}
            except Exception as exc:
                return {"error": f"EXPLAIN failed: {exc}"}

        def react_repair(state: QueryState) -> dict[str, Any]:
            """Observe a DB error, take one bounded repair action, then re-enter validation."""

            attempt = state.get("react_attempts", 0) + 1
            steps = list(state.get("react_steps", []))
            error = state.get("error") or "unknown database error"
            steps.append({"attempt": attempt, "phase": "observe", "error": error, "sql": (state.get("sql") or "")[:400]})
            if attempt > REACT_MAX_ATTEMPTS:
                steps.append({"attempt": attempt, "phase": "stop", "action": "repair_budget_exhausted"})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
                    "react_retry": False,
                    "error": f"ReAct repair budget exhausted after {REACT_MAX_ATTEMPTS} attempts: {error}",
                }
            if not self.llm:
                steps.append({"attempt": attempt, "phase": "stop", "action": "llm_unavailable"})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
                    "react_retry": False,
                    "error": f"Cannot repair SQL without an LLM: {error}",
                }
            try:
                critic_rejected = error.startswith("critic rejected")
                guidance = (
                    "The current query was rejected because it does not answer the question; write a new query that directly answers the question."
                    if critic_rejected
                    else "Keep answering the original question; make the smallest change that fixes the reported error instead of switching to an unrelated query."
                )
                if state.get("spec") is not None:
                    # Composed path: repair the JSON query plan, not the SQL text.
                    schema_map = _workspace_schema(self.workspace)
                    scope = set(state.get("schema_scope") or [])
                    plan = state.get("spec") or {}
                    mentioned = {str(plan.get("from") or "")}
                    mentioned |= {str(j.get("table") or "") for j in plan.get("joins", []) if isinstance(j, dict)}
                    mentioned |= {str(g.get("table") or "") for g in plan.get("group_by", []) if isinstance(g, dict)}
                    digest = _schema_digest(state.get("loaded_files", {}), (scope | mentioned) or None)
                    fixed_spec = self.llm.chat_json(
                        "You repair a structured query plan (JSON parts of a PostgreSQL query). Observe the "
                        "error and return the corrected plan. " + guidance,
                        json.dumps(
                            {
                                "question": state["question"],
                                "current_plan": state.get("spec"),
                                "observation": error,
                                "schema": digest,
                            },
                            ensure_ascii=False,
                        ),
                        schema=SPEC_JSON_SCHEMA,
                    )
                    if not isinstance(fixed_spec, dict) or not fixed_spec.get("from"):
                        raise ValueError("repair returned no valid query plan")
                    if fixed_spec == state.get("spec"):
                        steps.append({
                            "attempt": attempt,
                            "phase": "observe",
                            "error": "repair returned the same query plan; the next repair must materially change it",
                        })
                        return {
                            "react_attempts": attempt,
                            "react_steps": steps,
                            "react_repair_ready": False,
                            "react_retry": True,
                            "error": f"previous repair returned an unchanged query plan; change it to fix: {error}",
                        }
                    try:
                        repaired_sql = assemble_spec(fixed_spec, schema_map)
                    except ValueError as exc:
                        steps.append({
                            "attempt": attempt,
                            "phase": "observe",
                            "error": f"repaired plan still does not assemble: {exc}",
                        })
                        return {
                            "spec": fixed_spec,
                            "react_attempts": attempt,
                            "react_steps": steps,
                            "react_repair_ready": False,
                            "react_retry": True,
                            "error": f"repaired plan still does not assemble: {exc}",
                        }
                    steps.append({
                        "attempt": attempt,
                        "phase": "act",
                        "action": "repair_plan",
                        "sql": repaired_sql[:400],
                        "rationale": "schema-guided plan correction",
                    })
                    return {
                        "sql": repaired_sql,
                        "spec": fixed_spec,
                        "error": "",
                        "critic_rejected": False,
                        "react_attempts": attempt,
                        "react_steps": steps,
                        "react_repair_ready": True,
                        "react_retry": False,
                        "llm_used": True,
                    }
                answer = self.llm.chat_json(
                    """You are a bounded ReAct SQL repair agent. Observe the error and act by returning one corrected PostgreSQL query.
Rules:
- Output exactly one valid SELECT or WITH statement in standard SQL syntax — no prose, no markdown, no 'key': value notation.
- """
                    + guidance
                    + """
- Use only tables and columns that appear in the supplied schema context; never invent identifiers.
- Do not read system catalogs (information_schema, pg_catalog) unless the question explicitly asks about the schema itself.
Return JSON with sql and a short rationale.""",
                    json.dumps(
                        {
                            "question": state["question"],
                            "current_sql": state.get("sql"),
                            "observation": error,
                            "schema": _schema_digest(state.get("loaded_files", {})),
                            "identifier_notes": (state.get("loaded_files", {}).get("schema/identifier_notes.yaml", ""))[:800],
                        },
                        ensure_ascii=False,
                    ),
                    schema={
                        "type": "object",
                        "properties": {"sql": {"type": "string"}, "rationale": {"type": "string"}},
                        "required": ["sql"],
                    },
                )
                repaired_sql = _clean_sql(str(answer.get("sql", "")))
                if not repaired_sql or repaired_sql == state.get("sql"):
                    # An echoed query is another observation, not a terminal failure:
                    # feed it back so the next attempt must propose something different.
                    steps.append({
                        "attempt": attempt,
                        "phase": "observe",
                        "error": "repair returned the same SQL; the next repair must materially change the query",
                        "sql": repaired_sql[:400],
                    })
                    return {
                        "react_attempts": attempt,
                        "react_steps": steps,
                        "react_repair_ready": False,
                        "react_retry": True,
                        "error": f"previous repair returned unchanged SQL; propose a materially different query that fixes: {error}",
                    }
                steps.append({
                    "attempt": attempt,
                    "phase": "act",
                    "action": "repair_sql",
                    "sql": repaired_sql[:400],
                    "rationale": str(answer.get("rationale", "schema-guided correction"))[:240],
                })
                return {
                    "sql": repaired_sql,
                    "error": "",
                    "critic_rejected": False,
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": True,
                    "react_retry": False,
                    "llm_used": True,
                }
            except (LLMUnavailable, KeyError, ValueError, TypeError) as exc:
                steps.append({"attempt": attempt, "phase": "stop", "action": "repair_failed", "error": str(exc)[:240]})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
                    "react_retry": False,
                    "error": f"ReAct repair failed: {exc}; original error: {error}",
                }

        def executor(state: QueryState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                return {"result": self.db.execute(state["sql"]).as_json()}
            except Exception as exc:
                return {"error": f"execution failed: {exc}"}

        def invariants(state: QueryState) -> dict[str, Any]:
            if state.get("error"):
                return {"invariants": {"passed": False, "failures": [state["error"]]}}
            result = QueryResult(**state["result"])
            declared = (self.workspace.read_yaml("evals/invariants.yaml", default={}) or {}).get("invariants", [])
            return {"invariants": _invariant_check(result, declared)}

        def critic(state: QueryState) -> dict[str, Any]:
            """Truthfulness gate: does the executed query actually answer the question?

            A clean execution is not enough — the query may measure something unrelated
            (e.g. catalog metadata instead of business data). Rejections feed the ReAct
            repair loop with feedback and are persisted into the trajectory as a
            learning signal for evolution.
            """

            if state.get("error"):
                return {}
            sql_text = state.get("sql") or ""
            if metadata_drift(state["question"], sql_text):
                verdict = {
                    "answered": False,
                    "feedback": "the query reads catalog metadata, but the question asks about business data",
                }
            elif self.llm:
                result = state.get("result") or {}
                try:
                    answer = self.llm.chat_json(
                        "You verify that a SQL query and its result answer the user's question. Compare the "
                        "question intent (entity, metric, filters) with the query and the returned columns and "
                        "sample rows. Do not trust column aliases — they can be misleading; check which tables "
                        "the query actually reads. Mark answered=false when the query measures something else, "
                        "reads tables unrelated to the question's subject, answers about different entities, or "
                        "inspects metadata instead of data when the question asks about data. "
                        "Return JSON {answered: true|false, feedback: short concrete reason}.",
                        json.dumps(
                            {
                                "question": state["question"],
                                "sql": sql_text,
                                "columns": result.get("columns", []),
                                "sample_rows": (result.get("rows") or [])[:3],
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    )
                    verdict = {
                        "answered": bool(answer.get("answered", True)),
                        "feedback": str(answer.get("feedback", ""))[:300],
                    }
                except LLMUnavailable:
                    verdict = {"answered": True, "feedback": ""}
            else:
                verdict = {"answered": True, "feedback": ""}
            if not verdict["answered"]:
                return {
                    "critic": verdict,
                    "critic_rejected": True,
                    "error": f"critic rejected the answer: {verdict['feedback']}",
                }
            return {"critic": verdict}

        def persist(state: QueryState) -> dict[str, Any]:
            trajectory = {
                "question": state["question"],
                "route": state.get("route"),
                "template": state.get("template") or None,
                "loaded_files": state.get("selected_files", []),
                "plan": state.get("plan"),
                "sql": state.get("sql"),
                "explain": state.get("explain"),
                "result": state.get("result"),
                "invariants": state.get("invariants"),
                "critic": state.get("critic") or None,
                "error": state.get("error"),
                "llm_used": state.get("llm_used", False),
                "telemetry": state.get("telemetry", {
                    "ambiguity_detected": False,
                    "possible_metrics": [],
                    "clarification_requested": False,
                }),
                "clarification": state.get("clarification") or None,
                "spec": state.get("spec") or None,
                "react": {
                    "attempts": state.get("react_attempts", 0),
                    "steps": state.get("react_steps", []),
                },
            }
            append_trajectory(self.workspace.root / "experience" / "trajectories.jsonl", trajectory)
            _record_template_metrics(self.workspace, state)
            _learn_template(self.workspace, state)
            return {}

        graph.add_node("router", router)
        graph.add_node("loader", loader)
        graph.add_node("telemetry", telemetry)
        graph.add_node("planner", planner)
        graph.add_node("sql_generator", sql_generator)
        graph.add_node("validator", validator)
        graph.add_node("explain_gate", explainer)
        graph.add_node("react_repair", react_repair)
        graph.add_node("execute", executor)
        graph.add_node("invariant_check", invariants)
        graph.add_node("critic", critic)
        graph.add_node("persist", persist)
        graph.add_edge(START, "router")
        graph.add_edge("router", "loader")
        graph.add_edge("loader", "telemetry")
        graph.add_edge("telemetry", "planner")
        graph.add_conditional_edges(
            "planner",
            lambda state: "persist" if state.get("telemetry", {}).get("clarification_requested") else "sql_generator",
            {"persist": "persist", "sql_generator": "sql_generator"},
        )
        graph.add_edge("sql_generator", "validator")
        graph.add_conditional_edges(
            "validator",
            lambda state: "react_repair" if state.get("error") else "explain_gate",
            {"react_repair": "react_repair", "explain_gate": "explain_gate"},
        )
        graph.add_conditional_edges(
            "explain_gate",
            lambda state: "react_repair" if state.get("error") else "execute",
            {"react_repair": "react_repair", "execute": "execute"},
        )
        graph.add_conditional_edges(
            "execute",
            lambda state: "react_repair" if state.get("error") else "invariant_check",
            {"react_repair": "react_repair", "invariant_check": "invariant_check"},
        )
        graph.add_conditional_edges(
            "react_repair",
            lambda state: (
                "validator"
                if state.get("react_repair_ready")
                else ("react_repair" if state.get("react_retry") else "persist")
            ),
            {"validator": "validator", "react_repair": "react_repair", "persist": "persist"},
        )
        graph.add_edge("invariant_check", "critic")
        graph.add_conditional_edges(
            "critic",
            lambda state: "react_repair" if state.get("critic_rejected") else "persist",
            {"react_repair": "react_repair", "persist": "persist"},
        )
        graph.add_edge("persist", END)
        result = graph.compile().invoke({"question": question, "workspace_path": str(self.workspace.root)})
        return {key: value for key, value in result.items() if key not in {"loaded_files"}}


def ask(db: Database, workspace: Workspace, question: str, llm: OllamaClient | None = None) -> dict[str, Any]:
    return QueryAgent(db, workspace, llm).run(question)
