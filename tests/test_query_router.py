from sqlagent.query_agent.graph import (
    QueryAgent,
    detect_ambiguity,
    route_question,
)
from sqlagent.workspace import Workspace


MANIFEST = {
    "domains": {"sales": ["orders", "order_items"], "customers": ["customers"]},
    "templates": {
        "monthly_revenue": {
            "path": "templates/monthly_revenue.sql",
            "description": "revenue by month",
            "grain": "one row per month",
        }
    },
}


class FakeRouterLLM:
    def __init__(self, answer) -> None:
        self.answer = answer

    def chat_json(self, system, user, schema=None):
        return self.answer


def test_llm_router_selects_domain_and_template() -> None:
    route, files, template = route_question(
        "выручка по месяцам", manifest=MANIFEST, llm=FakeRouterLLM({"domain": "sales", "template": "monthly_revenue"})
    )

    assert route == "sales"
    assert template == "monthly_revenue"
    assert "domains/sales.yaml" in files
    assert "templates/monthly_revenue.sql" in files
    assert "manifest.yaml" in files


def test_router_without_llm_uses_generic_core_files() -> None:
    route, files, template = route_question("любой вопрос", manifest=MANIFEST, llm=None)

    assert route == ""
    assert template is None
    assert "domains/index.yaml" in files
    assert "schema/tables.yaml" in files


def test_router_ignores_unknown_llm_domain_and_template() -> None:
    route, files, template = route_question(
        "вопрос", manifest=MANIFEST, llm=FakeRouterLLM({"domain": "nope", "template": "nope"})
    )

    assert route == ""
    assert template is None
    assert "domains/index.yaml" in files


def test_question_without_template_and_llm_reports_honest_error(tmp_path) -> None:
    result = QueryAgent(None, Workspace(tmp_path / "skill")).run("Покажи остатки по складам")

    assert "No matching template" in result["error"]
    assert result.get("sql") is None


def test_ambiguous_question_records_metric_candidates_and_requests_clarification() -> None:
    telemetry = detect_ambiguity("какие показатели у бизнеса", ["monthly_revenue", "top_categories"])

    assert telemetry == {
        "ambiguity_detected": True,
        "possible_metrics": ["monthly_revenue", "top_categories"],
        "clarification_requested": True,
    }


def test_specific_metric_is_not_ambiguous() -> None:
    telemetry = detect_ambiguity("monthly revenue by region", ["monthly_revenue", "top_categories"])

    assert telemetry["ambiguity_detected"] is False
    assert telemetry["clarification_requested"] is False
    assert telemetry["possible_metrics"] == ["monthly_revenue"]


def test_ambiguous_query_persists_telemetry_without_running_sql(tmp_path) -> None:
    result = QueryAgent(None, Workspace(tmp_path / "skill")).run("какие показатели у бизнеса")

    assert result["telemetry"]["clarification_requested"] is True
    assert result["clarification"]
    assert result.get("sql") is None
