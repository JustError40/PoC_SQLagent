from __future__ import annotations

import json
import re
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
    semantics: dict[str, dict[str, str]]
    domains: dict[str, list[str]]
    workspace_path: str
    llm_used: bool


DOMAIN_MAP = {
    "sales": ["orders", "order_items", "order_payments", "shipments", "returns", "stores"],
    "customers": ["customers", "customer_campaigns", "marketing_campaigns"],
    "logistics": ["shipments", "stores", "employees"],
    "finance": ["order_payments", "expenses", "daily_fx_rates"],
    "inventory": ["products", "inventory_snapshots", "suppliers", "product_suppliers"],
}

DESCRIPTIONS = {
    "customers": "Customer master with segment, region, signup date and soft deletion.",
    "products": "Sellable product catalog with category, price and cost.",
    "orders": "Order-level sales facts partitioned by order date; total_amount is already order grain.",
    "order_items": "Line-item facts; joining them to orders changes the grain to item level.",
    "order_payments": "Payment events; multiple rows can belong to one order and cause fanout.",
    "shipments": "Shipment status and delivery timestamps, normally at most one row per order.",
    "returns": "Returned order items and return reasons.",
    "stores": "Retail store master and region.",
    "marketing_campaigns": "Campaign calendar and acquisition channel.",
    "customer_campaigns": "Many-to-many customer acquisition attribution.",
    "employees": "Employees assigned to stores.",
    "suppliers": "Supplier master.",
    "product_suppliers": "Product-to-supplier relationship with lead time.",
    "inventory_snapshots": "Periodic product stock snapshots by warehouse.",
    "expenses": "Store operating expenses by day and category.",
    "daily_fx_rates": "Daily currency exchange rates.",
}


def _fetch_rows(conn: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(query, params) if params else conn.execute(query)
    columns = [description.name for description in cursor.description or []]
    return [json_safe(dict(zip(columns, row))) for row in cursor.fetchall()]


def inventory_node(state: SurveyState, *, db: Database) -> dict[str, Any]:
    with psycopg.connect(db.dsn) as conn:
        tables = _fetch_rows(
            conn,
            """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
              AND table_name NOT LIKE 'orders_%'
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
    return {"inventory": tables, "columns": columns, "constraints": constraints, "indexes": indexes}


def profiling_node(state: SurveyState, *, db: Database) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}
    with psycopg.connect(db.dsn) as conn:
        for table, columns in state["columns"].items():
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
            profiles[table] = table_profile
    return {"profiles": profiles}


def semantics_node(state: SurveyState, *, llm: OllamaClient | None = None) -> dict[str, Any]:
    semantics = {
        table: {
            "description": DESCRIPTIONS.get(table, f"Warehouse table {table}."),
            "grain": "one row per " + ("order" if table == "orders" else table.rstrip("s")),
        }
        for table in state["columns"]
    }
    used = False
    if llm:
        prompt = json.dumps(
            {table: [column["column_name"] for column in columns] for table, columns in state["columns"].items()},
            ensure_ascii=False,
        )
        try:
            answer = llm.chat_json(
                "Describe warehouse tables. Return JSON object table -> {description, grain}. Keep facts concise.",
                prompt,
            )
            for table, value in answer.items():
                if table in semantics and isinstance(value, dict):
                    semantics[table].update({key: str(val) for key, val in value.items() if key in {"description", "grain"}})
            used = True
        except LLMUnavailable:
            pass
    return {"semantics": semantics, "llm_used": used}


def domains_node(state: SurveyState) -> dict[str, Any]:
    known = set(state["columns"])
    domains = {domain: [table for table in tables if table in known] for domain, tables in DOMAIN_MAP.items()}
    remaining = sorted(known - {table for tables in domains.values() for table in tables})
    if remaining:
        domains["other"] = remaining
    return {"domains": domains}


def _template_files() -> dict[str, str]:
    return {
        "monthly_revenue.sql": """-- order grain: do not join order_payments or order_items for this metric\nSELECT date_trunc('month', order_date)::date AS month,\n       round(sum(total_amount)::numeric, 2) AS revenue\nFROM orders\nWHERE NOT is_deleted AND status <> 'cancelled'\nGROUP BY 1 ORDER BY 1;\n""",
        "new_customer_revenue.sql": """WITH first_orders AS (\n  SELECT customer_id, min(order_date) AS first_order_date\n  FROM orders WHERE NOT is_deleted AND status <> 'cancelled'\n  GROUP BY customer_id\n)\nSELECT date_trunc('month', o.order_date)::date AS month,\n       round(sum(o.total_amount)::numeric, 2) AS revenue\nFROM orders o\nJOIN first_orders f ON f.customer_id = o.customer_id\n  AND f.first_order_date = o.order_date\nWHERE NOT o.is_deleted AND o.status <> 'cancelled'\nGROUP BY 1 ORDER BY 1;\n""",
        "top_categories.sql": """SELECT p.category, round(sum(i.quantity * i.unit_price)::numeric, 2) AS revenue\nFROM order_items i\nJOIN products p ON p.id = i.product_id\nGROUP BY p.category ORDER BY revenue DESC;\n""",
        "revenue_by_region.sql": """SELECT s.region, round(sum(o.total_amount)::numeric, 2) AS revenue\nFROM orders o JOIN stores s ON s.id = o.store_id\nWHERE NOT o.is_deleted AND o.status <> 'cancelled'\nGROUP BY s.region ORDER BY revenue DESC;\n""",
        "on_time_delivery.sql": """SELECT round(100.0 * avg((delivered_at <= shipped_at + interval '5 days')::int), 2) AS on_time_percent\nFROM shipments WHERE status = 'delivered';\n""",
        "product_quarterly_growth.sql": """WITH quarterly_sales AS (\n  SELECT oi.product_id, date_trunc('quarter', oi.order_date)::date AS quarter,\n         sum(oi.quantity * oi.unit_price)::numeric AS sales\n  FROM order_items oi JOIN orders o ON o.id = oi.order_id\n  WHERE NOT o.is_deleted AND o.status <> 'cancelled'\n  GROUP BY oi.product_id, date_trunc('quarter', oi.order_date)::date\n), history AS (\n  SELECT product_id, quarter, sales,\n         lag(quarter, 1) OVER (PARTITION BY product_id ORDER BY quarter) AS previous_quarter,\n         lag(quarter, 2) OVER (PARTITION BY product_id ORDER BY quarter) AS two_quarters_ago,\n         lag(sales, 1) OVER (PARTITION BY product_id ORDER BY quarter) AS previous_sales,\n         lag(sales, 2) OVER (PARTITION BY product_id ORDER BY quarter) AS two_quarters_ago_sales\n  FROM quarterly_sales\n)\nSELECT DISTINCT ON (h.product_id) p.id AS product_id, p.name, h.quarter AS latest_quarter,\n       round(h.two_quarters_ago_sales, 2) AS sales_two_quarters_ago,\n       round(h.previous_sales, 2) AS sales_previous_quarter,\n       round(h.sales, 2) AS sales_latest_quarter\nFROM history h JOIN products p ON p.id = h.product_id\nWHERE h.previous_quarter = (h.two_quarters_ago + interval '3 months')::date\n  AND h.quarter = (h.previous_quarter + interval '3 months')::date\n  AND h.two_quarters_ago_sales < h.previous_sales\n  AND h.previous_sales < h.sales\nORDER BY h.product_id, h.quarter DESC;\n""",
    }


def save_node(state: SurveyState) -> dict[str, Any]:
    workspace = Workspace(Path(state["workspace_path"]))
    workspace.ensure_git()
    workspace.write_text(".gitignore", "experience/trajectories.jsonl\n.cache/\n")
    if workspace._git("ls-files", "--error-unmatch", "experience/trajectories.jsonl", check=False):
        workspace._git("rm", "--cached", "--ignore-unmatch", "experience/trajectories.jsonl")
    workspace.write_text(
        "SKILL.md",
        """# warehouse_prod skill\n\n## Router\nUse `manifest.yaml` first, then load only the domain and artifact files selected for the question.\n\n## Query protocol\n1. Identify the metric grain. 2. Prefer a template. 3. Keep queries read-only.\n4. Run EXPLAIN before execution. 5. Check invariants before returning results.\n\n## Grain rules\n`orders.total_amount` is order grain. `order_items` and `order_payments` are one-to-many\nrelations and must not be joined when aggregating order-level measures unless pre-aggregated.\n""",
    )
    manifest = {
        "version": 1,
        "workspace": "warehouse_prod",
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
    }
    workspace.write_yaml("manifest.yaml", manifest)
    workspace.write_yaml(
        "schema/tables.yaml",
        {"tables": [{"name": table, "description": state["semantics"][table]["description"], "columns": columns} for table, columns in state["columns"].items()]},
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
    workspace.write_yaml(
        "relationships/verified_joins.yaml",
        {
            "joins": [
                {"left": "orders.customer_id", "right": "customers.id", "cardinality": "many_to_one", "verified": True},
                {"left": "orders.store_id", "right": "stores.id", "cardinality": "many_to_one", "verified": True},
                {"left": "order_items.product_id", "right": "products.id", "cardinality": "many_to_one", "verified": True},
                {"left": "shipments.order_id", "right": "orders.id", "cardinality": "one_to_one_expected", "verified": True},
                {"left": "customers.id", "right": "customer_campaigns.customer_id", "cardinality": "one_to_many", "verified": True},
            ]
        },
    )
    workspace.write_yaml(
        "relationships/dangerous_joins.yaml",
        {
            "joins": [
                {"left": "orders.id", "right": "order_items.order_id", "reason": "line-item fanout", "required_action": "preaggregate or use item grain"},
                {"left": "orders.id", "right": "order_payments.order_id", "reason": "payment-event fanout", "required_action": "preaggregate before joining order measures"},
            ]
        },
    )
    workspace.write_yaml("policies/forbidden_operations.yaml", {"read_only": True, "forbidden_tables": ["pg_authid", "pg_shadow"], "max_result_rows": 500, "explain_required": True})
    workspace.write_yaml(
        "evals/invariants.yaml",
        {"invariants": [{"id": "non_negative_revenue", "expression": "revenue >= 0"}, {"id": "no_order_fanout", "expression": "order-level sums do not multiply after one-to-many joins"}, {"id": "bounded_result", "expression": "rows <= 500"}]},
    )
    for relative, content in _template_files().items():
        workspace.write_text(f"templates/{relative}", content)
    exploration = [
        {"question": "monthly revenue", "template": "templates/monthly_revenue.sql", "status": "verified"},
        {"question": "new customer revenue by month", "template": "templates/new_customer_revenue.sql", "status": "verified"},
        {"question": "revenue by region", "template": "templates/revenue_by_region.sql", "status": "verified"},
        {"question": "top categories", "template": "templates/top_categories.sql", "status": "verified"},
        {"question": "on time delivery", "template": "templates/on_time_delivery.sql", "status": "verified"},
    ]
    workspace.write_text("experience/synthetic_exploration.jsonl", "\n".join(json.dumps(item, ensure_ascii=False) for item in exploration) + "\n")
    workspace.write_text("experience/trajectories.jsonl", "")
    workspace.commit("survey: generate warehouse skill workspace")
    return {"workspace": str(workspace.root), "tables": len(state["columns"]), "llm_used": state.get("llm_used", False)}


def run_survey(db: Database, workspace: Workspace, llm: OllamaClient | None = None) -> dict[str, Any]:
    """Run the inventory -> profiling -> semantics -> domains -> save graph."""

    def inventory(state: SurveyState) -> dict[str, Any]:
        return inventory_node(state, db=db)

    def profiling(state: SurveyState) -> dict[str, Any]:
        return profiling_node(state, db=db)

    def semantics(state: SurveyState) -> dict[str, Any]:
        return semantics_node(state, llm=llm)

    def save(state: SurveyState) -> dict[str, Any]:
        return save_node(state)

    graph = StateGraph(SurveyState)
    graph.add_node("inventory", inventory)
    graph.add_node("profiling", profiling)
    graph.add_node("semantics", semantics)
    graph.add_node("domains", domains_node)
    graph.add_node("save", save)
    graph.add_edge(START, "inventory")
    graph.add_edge("inventory", "profiling")
    graph.add_edge("profiling", "semantics")
    graph.add_edge("semantics", "domains")
    graph.add_edge("domains", "save")
    graph.add_edge("save", END)
    result = graph.compile().invoke({"workspace_path": str(workspace.root)})
    return {"workspace": str(workspace.root), "tables": len(result.get("columns", {})), "llm_used": result.get("llm_used", False)}
