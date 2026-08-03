from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from sqlagent.db import Database, QueryResult, QuerySafetyError
from sqlagent.llm import LLMUnavailable, OllamaClient
from sqlagent.trajectories import append_trajectory
from sqlagent.workspace import Workspace


class QueryState(TypedDict, total=False):
    question: str
    workspace_path: str
    selected_files: list[str]
    loaded_files: dict[str, str]
    route: str
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


POSSIBLE_METRICS = [
    "net_revenue",
    "net_profit",
    "customer_count",
    "year_over_year_growth",
]

_METRIC_TERMS = {
    "net_revenue": ("выруч", "revenue", "sales", "доход"),
    "net_profit": ("прибыл", "profit", "марж"),
    "customer_count": ("клиент", "customer", "покупател"),
    "year_over_year_growth": ("рост", "динамик", "year over year", "yoy", "год к году"),
}
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
REACT_MAX_ATTEMPTS = 2


def _is_product_sales_growth_question(question: str) -> bool:
    normalized = question.lower()
    return (
        any(word in normalized for word in ("товар", "продукт", "product"))
        and any(word in normalized for word in ("продаж", "выруч", "sales", "revenue"))
        and any(word in normalized for word in ("рост", "динамик", "growth", "три квартал", "three quarter"))
    )


def _product_quarterly_growth_sql() -> str:
    return """WITH quarterly_sales AS (
    SELECT oi.product_id,
           date_trunc('quarter', oi.order_date)::date AS quarter,
           sum(oi.quantity * oi.unit_price)::numeric AS sales
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    WHERE NOT o.is_deleted AND o.status <> 'cancelled'
    GROUP BY oi.product_id, date_trunc('quarter', oi.order_date)::date
), history AS (
    SELECT product_id,
           quarter,
           sales,
           lag(quarter, 1) OVER (PARTITION BY product_id ORDER BY quarter) AS previous_quarter,
           lag(quarter, 2) OVER (PARTITION BY product_id ORDER BY quarter) AS two_quarters_ago,
           lag(sales, 1) OVER (PARTITION BY product_id ORDER BY quarter) AS previous_sales,
           lag(sales, 2) OVER (PARTITION BY product_id ORDER BY quarter) AS two_quarters_ago_sales
    FROM quarterly_sales
)
SELECT DISTINCT ON (h.product_id)
       p.id AS product_id,
       p.name,
       h.quarter AS latest_quarter,
       round(h.two_quarters_ago_sales, 2) AS sales_two_quarters_ago,
       round(h.previous_sales, 2) AS sales_previous_quarter,
       round(h.sales, 2) AS sales_latest_quarter
FROM history h
JOIN products p ON p.id = h.product_id
WHERE h.previous_quarter = (h.two_quarters_ago + interval '3 months')::date
  AND h.quarter = (h.previous_quarter + interval '3 months')::date
  AND h.two_quarters_ago_sales < h.previous_sales
  AND h.previous_sales < h.sales
ORDER BY h.product_id, h.quarter DESC;"""


def detect_ambiguity(question: str) -> dict[str, Any]:
    """Return a stable, model-independent ambiguity telemetry payload."""

    normalized = question.lower()
    explicit_metrics = [
        metric for metric, terms in _METRIC_TERMS.items() if any(term in normalized for term in terms)
    ]
    ambiguous = any(term in normalized for term in _AMBIGUITY_TERMS)
    if not explicit_metrics and any(term in normalized for term in ("что важнее", "что показать", "главн")):
        ambiguous = True
    return {
        "ambiguity_detected": ambiguous,
        "possible_metrics": POSSIBLE_METRICS.copy() if ambiguous else explicit_metrics,
        "clarification_requested": ambiguous,
    }


def clarification_prompt(telemetry: dict[str, Any]) -> str:
    metrics = ", ".join(telemetry.get("possible_metrics", POSSIBLE_METRICS))
    return f"Уточните, какую метрику посчитать: {metrics}."


def route_question(question: str) -> tuple[str, list[str]]:
    normalized = question.lower()
    if _is_product_sales_growth_question(normalized):
        route = "sales"
    elif any(word in normalized for word in ("клиент", "customer", "покупател")):
        route = "customers"
    elif any(word in normalized for word in ("достав", "shipment", "логист")):
        route = "logistics"
    elif any(word in normalized for word in ("склад", "остат", "inventory", "товар")):
        route = "inventory"
    elif any(word in normalized for word in ("оплат", "расход", "марж", "финанс", "payment")):
        route = "finance"
    else:
        route = "sales"

    files = [
        "SKILL.md",
        "manifest.yaml",
        f"domains/{route}.yaml",
        "schema/tables.yaml",
        "relationships/dangerous_joins.yaml",
        "evals/invariants.yaml",
    ]
    if any(word in normalized for word in ("новых клиент", "new customer")):
        files.append("templates/new_customer_revenue.sql")
    elif (any(word in normalized for word in ("выруч", "revenue", "продаж")) and "месяц" in normalized) or "monthly" in normalized:
        files.append("templates/monthly_revenue.sql")
    elif any(word in normalized for word in ("категор", "category")):
        files.append("templates/top_categories.sql")
    elif any(word in normalized for word in ("регион", "region")):
        files.append("templates/revenue_by_region.sql")
    elif any(word in normalized for word in ("достав", "on time", "срок")):
        files.append("templates/on_time_delivery.sql")
    elif any(word in normalized for word in ("оплат", "payment")) and any(word in normalized for word in ("выруч", "revenue")):
        files.append("templates/payment_revenue.sql")
    if _is_product_sales_growth_question(normalized):
        files.append("templates/product_quarterly_growth.sql")
    return route, files


def _template_for(question: str) -> str | None:
    normalized = question.lower()
    if _is_product_sales_growth_question(normalized):
        return "templates/product_quarterly_growth.sql"
    if ("новых клиент" in normalized or "new customer" in normalized) and ("выруч" in normalized or "revenue" in normalized):
        return "templates/new_customer_revenue.sql"
    if any(word in normalized for word in ("выруч", "revenue", "продаж")) and ("месяц" in normalized or "monthly" in normalized):
        return "templates/monthly_revenue.sql"
    if any(word in normalized for word in ("категор", "category")):
        return "templates/top_categories.sql"
    if any(word in normalized for word in ("регион", "region")) and any(word in normalized for word in ("выруч", "revenue")):
        return "templates/revenue_by_region.sql"
    if any(word in normalized for word in ("достав", "on time", "срок")):
        return "templates/on_time_delivery.sql"
    if any(word in normalized for word in ("оплат", "payment")) and any(word in normalized for word in ("выруч", "revenue")):
        return "templates/payment_revenue.sql"
    return None


def _fallback_sql(question: str) -> str:
    normalized = question.lower()
    if ("заказ" in normalized and "статус" in normalized) or "orders by status" in normalized:
        return "SELECT status, count(*) AS orders FROM orders WHERE NOT is_deleted GROUP BY status ORDER BY orders DESC;"
    if "клиент" in normalized and "регион" in normalized:
        return """SELECT c.region, count(DISTINCT c.id) AS customers
FROM customers c WHERE NOT c.is_deleted GROUP BY c.region ORDER BY customers DESC;"""
    raise ValueError("No verified template or deterministic fallback matches this question")


def _clean_sql(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^```(?:sql)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            value = str(parsed.get("sql", value))
        except json.JSONDecodeError:
            pass
    return value.strip()


def _invariant_check(result: QueryResult) -> dict[str, Any]:
    failures: list[str] = []
    for row in result.rows:
        for key, value in row.items():
            if key.lower() in {"revenue", "amount", "total_amount", "profit"} and isinstance(value, (int, float)) and value < 0:
                failures.append(f"{key} is negative")
    return {"passed": not failures and len(result.rows) <= 500, "failures": failures, "rows": len(result.rows)}


class QueryAgent:
    def __init__(self, db: Database, workspace: Workspace, llm: OllamaClient | None = None) -> None:
        self.db = db
        self.workspace = workspace
        self.llm = llm

    def run(self, question: str) -> dict[str, Any]:
        graph = StateGraph(QueryState)

        def router(state: QueryState) -> dict[str, Any]:
            route, files = route_question(state["question"])
            return {"route": route, "selected_files": files}

        def loader(state: QueryState) -> dict[str, Any]:
            loaded = {}
            for relative in state["selected_files"]:
                path = self.workspace.root / relative
                if path.exists():
                    loaded[relative] = path.read_text(encoding="utf-8")
            return {"loaded_files": loaded}

        def telemetry(state: QueryState) -> dict[str, Any]:
            payload = detect_ambiguity(state["question"])
            return {
                "telemetry": payload,
                "clarification": clarification_prompt(payload) if payload["clarification_requested"] else "",
            }

        def planner(state: QueryState) -> dict[str, Any]:
            if state.get("telemetry", {}).get("clarification_requested"):
                return {"plan": "request metric clarification before generating SQL"}
            template = _template_for(state["question"])
            if template and template in state["loaded_files"]:
                return {"plan": f"reuse template {template} at its documented grain"}
            return {"plan": "select the smallest verified domain, identify grain, generate one read-only query"}

        def sql_generator(state: QueryState) -> dict[str, Any]:
            template = _template_for(state["question"])
            if template and template in state["loaded_files"]:
                return {"sql": _clean_sql(state["loaded_files"][template]), "llm_used": False}
            if _is_product_sales_growth_question(state["question"]):
                return {"sql": _product_quarterly_growth_sql(), "llm_used": False}
            normalized = state["question"].lower()
            known_fallback = (
                (("заказ" in normalized and "статус" in normalized) or "orders by status" in normalized)
                or ("клиент" in normalized and "регион" in normalized)
                or (any(word in normalized for word in ("оплат", "payment")) and any(word in normalized for word in ("выруч", "revenue")))
            )
            if known_fallback:
                return {"sql": _fallback_sql(state["question"]), "llm_used": False}
            if self.llm:
                try:
                    answer = self.llm.chat_json(
                        "You generate PostgreSQL SELECT only. Return JSON {sql: string}. Respect table grain and no writes.",
                        json.dumps({"question": state["question"], "context": state["loaded_files"]}, ensure_ascii=False),
                    )
                    return {"sql": _clean_sql(str(answer["sql"])), "llm_used": True}
                except (LLMUnavailable, KeyError, ValueError, TypeError) as exc:
                    return {"error": f"SQL generation failed: {exc}", "llm_used": False}
            try:
                return {"sql": _fallback_sql(state["question"]), "llm_used": False}
            except ValueError as exc:
                return {"error": str(exc), "llm_used": False}

        def validator(state: QueryState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                from sqlagent.db import validate_read_only

                return {"sql": validate_read_only(state["sql"])}
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
            steps.append({"attempt": attempt, "phase": "observe", "error": error})
            if attempt > REACT_MAX_ATTEMPTS:
                steps.append({"attempt": attempt, "phase": "stop", "action": "repair_budget_exhausted"})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
                    "error": f"ReAct repair budget exhausted after {REACT_MAX_ATTEMPTS} attempts: {error}",
                }
            if not self.llm:
                steps.append({"attempt": attempt, "phase": "stop", "action": "llm_unavailable"})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
                    "error": f"Cannot repair SQL without an LLM: {error}",
                }
            try:
                answer = self.llm.chat_json(
                    """You are a bounded ReAct SQL repair agent. Observe the PostgreSQL error and act by returning a corrected PostgreSQL SELECT/WITH query.
Use only tables and columns present in the supplied schema. Do not invent identifiers, do not write data, and do not return chain-of-thought. Return JSON with sql and a short rationale.""",
                    json.dumps(
                        {
                            "question": state["question"],
                            "current_sql": state.get("sql"),
                            "observation": error,
                            "schema_context": state.get("loaded_files", {}),
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
                    raise ValueError("repair returned no changed SQL")
                steps.append({
                    "attempt": attempt,
                    "phase": "act",
                    "action": "repair_sql",
                    "rationale": str(answer.get("rationale", "schema-guided correction"))[:240],
                })
                return {
                    "sql": repaired_sql,
                    "error": "",
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": True,
                    "llm_used": True,
                }
            except (LLMUnavailable, KeyError, ValueError, TypeError) as exc:
                steps.append({"attempt": attempt, "phase": "stop", "action": "repair_failed", "error": str(exc)[:240]})
                return {
                    "react_attempts": attempt,
                    "react_steps": steps,
                    "react_repair_ready": False,
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
            return {"invariants": _invariant_check(result)}

        def persist(state: QueryState) -> dict[str, Any]:
            trajectory = {
                "question": state["question"],
                "route": state.get("route"),
                "loaded_files": state.get("selected_files", []),
                "plan": state.get("plan"),
                "sql": state.get("sql"),
                "explain": state.get("explain"),
                "result": state.get("result"),
                "invariants": state.get("invariants"),
                "error": state.get("error"),
                "llm_used": state.get("llm_used", False),
                "telemetry": state.get("telemetry", {
                    "ambiguity_detected": False,
                    "possible_metrics": [],
                    "clarification_requested": False,
                }),
                "clarification": state.get("clarification") or None,
                "react": {
                    "attempts": state.get("react_attempts", 0),
                    "steps": state.get("react_steps", []),
                },
            }
            append_trajectory(self.workspace.root / "experience" / "trajectories.jsonl", trajectory)
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
            lambda state: "validator" if state.get("react_repair_ready") else "persist",
            {"validator": "validator", "persist": "persist"},
        )
        graph.add_edge("invariant_check", "persist")
        graph.add_edge("persist", END)
        result = graph.compile().invoke({"question": question, "workspace_path": str(self.workspace.root)})
        return {key: value for key, value in result.items() if key not in {"loaded_files"}}


def ask(db: Database, workspace: Workspace, question: str, llm: OllamaClient | None = None) -> dict[str, Any]:
    return QueryAgent(db, workspace, llm).run(question)
