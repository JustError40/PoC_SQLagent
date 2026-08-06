import pytest

from sqlagent.composer import assemble_spec

SCHEMA = {
    "web_sales": ["ws_bill_addr_sk", "ws_net_paid", "ws_sold_date_sk"],
    "customer_address": ["ca_address_sk", "ca_state"],
    "date_dim": ["d_date_sk", "d_year"],
}


def test_assemble_grouped_measure_with_join() -> None:
    spec = {
        "from": "web_sales",
        "joins": [{"table": "customer_address", "left": "ws_bill_addr_sk", "right": "ca_address_sk"}],
        "group_by": [{"table": "customer_address", "column": "ca_state"}],
        "measure": {"agg": "sum", "table": "web_sales", "column": "ws_net_paid", "alias": "internet_revenue"},
        "order": {"by": "internet_revenue", "dir": "desc"},
        "limit": 20,
    }
    sql = assemble_spec(spec, SCHEMA)
    assert sql == (
        'SELECT "customer_address"."ca_state" AS "ca_state", '
        'SUM("web_sales"."ws_net_paid") AS "internet_revenue" '
        'FROM "web_sales" JOIN "customer_address" '
        'ON "web_sales"."ws_bill_addr_sk" = "customer_address"."ca_address_sk" '
        'GROUP BY "customer_address"."ca_state" ORDER BY "internet_revenue" DESC LIMIT 20'
    )


def test_assemble_filters_and_limit_clamp() -> None:
    spec = {
        "from": "web_sales",
        "measure": {"agg": "count", "column": "*"},
        "filters": [{"table": "web_sales", "column": "ws_net_paid", "op": ">", "value": 100}],
        "limit": 99999,
    }
    sql = assemble_spec(spec, SCHEMA)
    assert 'COUNT(*) AS "count"' in sql
    assert '"web_sales"."ws_net_paid" > 100' in sql
    assert sql.endswith("LIMIT 500")


def test_assemble_escapes_string_literals() -> None:
    spec = {
        "from": "customer_address",
        "measure": {"agg": "count", "column": "*"},
        "filters": [{"column": "ca_state", "op": "=", "value": "O'Hara'); DROP TABLE users; --"}],
    }
    sql = assemble_spec(spec, SCHEMA)
    assert "'O''Hara''); DROP TABLE users; --'" in sql
    assert sql.startswith("SELECT")


@pytest.mark.parametrize(
    "spec, message",
    [
        ({"from": "nope", "measure": {"agg": "count", "column": "*"}}, "unknown table"),
        ({"from": "web_sales", "measure": {"agg": "sum", "column": "nope"}}, "unknown column"),
        ({"from": "web_sales", "measure": {"agg": "median", "column": "ws_net_paid"}}, "unsupported aggregation"),
        ({"from": "web_sales", "group_by": [{"table": "date_dim", "column": "d_year"}]}, "not joined"),
        ({"from": "web_sales", "joins": [{"table": "date_dim", "left": "nope", "right": "d_date_sk"}]}, "unknown join column"),
        ({"from": "web_sales"}, "selects nothing"),
    ],
)
def test_assemble_rejects_bad_plans_with_precise_errors(spec, message) -> None:
    with pytest.raises(ValueError, match=message):
        assemble_spec(spec, SCHEMA)


def test_order_by_must_reference_selected_output() -> None:
    spec = {
        "from": "web_sales",
        "group_by": [{"column": "ws_sold_date_sk"}],
        "measure": {"agg": "count", "column": "*"},
        "order": {"by": "ca_state", "dir": "asc"},
    }
    with pytest.raises(ValueError, match="order column is not selected"):
        assemble_spec(spec, SCHEMA)


TABLES_YAML = {
    "tables": [
        {"name": "web_sales", "columns": [{"column_name": c} for c in SCHEMA["web_sales"]]},
        {"name": "customer_address", "columns": [{"column_name": c} for c in SCHEMA["customer_address"]]},
        {"name": "date_dim", "columns": [{"column_name": c} for c in SCHEMA["date_dim"]]},
    ]
}

GOOD_SPEC = {
    "from": "web_sales",
    "joins": [{"table": "customer_address", "left": "ws_bill_addr_sk", "right": "ca_address_sk"}],
    "group_by": [{"table": "customer_address", "column": "ca_state"}],
    "measure": {"agg": "sum", "column": "ws_net_paid", "alias": "internet_revenue"},
    "order": {"by": "internet_revenue", "dir": "desc"},
    "limit": 5,
}


class FakeDatabase:
    def explain(self, query):
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        from sqlagent.db import QueryResult

        return QueryResult(columns=["ca_state", "internet_revenue"], rows=[{"ca_state": "CA", "internet_revenue": 10}], elapsed_ms=0.2)


def _workspace(tmp_path):
    from sqlagent.workspace import Workspace

    workspace = Workspace(tmp_path / "skill")
    workspace.write_yaml("schema/tables.yaml", TABLES_YAML)
    return workspace


def test_agent_composes_query_from_json_plan(tmp_path) -> None:
    from sqlagent.query_agent.graph import QueryAgent

    class PlanLLM:
        def chat_json(self, system, user, schema=None):
            if "JSON parts" in system:
                return dict(GOOD_SPEC)
            if "You verify that a SQL query" in system:
                return {"answered": True, "feedback": ""}
            raise AssertionError(f"unexpected LLM call: {system[:60]}")

    workspace = _workspace(tmp_path)
    result = QueryAgent(FakeDatabase(), workspace, PlanLLM()).run("интернет-выручка по штатам")

    assert not result.get("error")
    assert '"customer_address"."ca_state"' in result["sql"]
    assert result["spec"]["from"] == "web_sales"
    # the verified answer was learned back into the skill as a reusable template
    templates = workspace.read_yaml("manifest.yaml")["templates"]
    learned = [meta for meta in templates.values() if meta.get("source") == "query_agent"]
    assert learned and learned[0]["status"] == "ok"


def test_agent_repairs_query_plan_part_by_part(tmp_path) -> None:
    from sqlagent.query_agent.graph import QueryAgent

    class RepairingPlanLLM:
        def __init__(self) -> None:
            self.calls = 0

        def chat_json(self, system, user, schema=None):
            self.calls += 1
            if "structured query plan" in system:
                return dict(GOOD_SPEC)
            if "JSON parts" in system:
                bad = dict(GOOD_SPEC)
                bad["measure"] = {"agg": "sum", "column": "ws_wrong", "alias": "internet_revenue"}
                return bad
            if "You verify that a SQL query" in system:
                return {"answered": True, "feedback": ""}
            raise AssertionError(f"unexpected LLM call: {system[:60]}")

    result = QueryAgent(FakeDatabase(), _workspace(tmp_path), RepairingPlanLLM()).run("интернет-выручка по штатам")

    assert not result.get("error")
    assert result["react_attempts"] == 1
    assert result["react_steps"][1]["action"] == "repair_plan"
    assert "ws_net_paid" in result["sql"]


def test_agent_stops_cleanly_when_model_repeats_a_broken_plan(tmp_path) -> None:
    from sqlagent.query_agent.graph import QueryAgent

    class StuckLLM:
        def chat_json(self, system, user, schema=None):
            if "JSON parts" in system or "structured query plan" in system:
                return {"from": "web_sales", "measure": {"agg": "sum", "column": "ws_wrong", "alias": "x"}}
            if "You verify that a SQL query" in system:
                return {"answered": True, "feedback": ""}
            raise AssertionError(f"unexpected LLM call: {system[:60]}")

    result = QueryAgent(FakeDatabase(), _workspace(tmp_path), StuckLLM()).run("сумма продаж")

    assert "budget exhausted" in result["error"]
    assert result["react_attempts"] > 1
