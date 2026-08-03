from sqlagent.query_agent.graph import (
    QueryAgent,
    _product_quarterly_growth_sql,
    detect_ambiguity,
    route_question,
)
from sqlagent.workspace import Workspace


def test_customer_question_loads_customer_domain_and_template() -> None:
    route, files = route_question("выручка новых клиентов по месяцам")
    assert route == "customers"
    assert "domains/customers.yaml" in files
    assert "templates/new_customer_revenue.sql" in files


def test_category_question_loads_sales_template() -> None:
    route, files = route_question("топ категорий по выручке")
    assert route == "sales"
    assert "templates/top_categories.sql" in files


def test_product_growth_question_uses_quarterly_sales_context() -> None:
    route, files = route_question("Покажи товары с ростом продаж три квартала подряд")

    assert route == "sales"
    assert "domains/sales.yaml" in files
    assert "templates/product_quarterly_growth.sql" in files
    sql = _product_quarterly_growth_sql()
    assert "date_trunc('quarter'" in sql
    assert "lag(sales, 2)" in sql
    assert "sales_latest_quarter" in sql


def test_unknown_question_does_not_fall_back_to_unrelated_monthly_revenue(tmp_path) -> None:
    result = QueryAgent(None, Workspace(tmp_path / "skill")).run("Покажи остатки по складам")

    assert "No verified template or deterministic fallback matches this question" in result["error"]
    assert result.get("sql") is None


def test_ambiguous_question_records_metric_candidates_and_requests_clarification() -> None:
    telemetry = detect_ambiguity("какие показатели у бизнеса")

    assert telemetry == {
        "ambiguity_detected": True,
        "possible_metrics": ["net_revenue", "net_profit", "customer_count", "year_over_year_growth"],
        "clarification_requested": True,
    }


def test_specific_metric_is_not_ambiguous() -> None:
    telemetry = detect_ambiguity("выручка по месяцам")

    assert telemetry["ambiguity_detected"] is False
    assert telemetry["clarification_requested"] is False


def test_ambiguous_query_persists_telemetry_without_running_sql(tmp_path) -> None:
    result = QueryAgent(None, Workspace(tmp_path / "skill")).run("какие показатели у бизнеса")

    assert result["telemetry"]["clarification_requested"] is True
    assert result["telemetry"]["possible_metrics"] == [
        "net_revenue",
        "net_profit",
        "customer_count",
        "year_over_year_growth",
    ]
    assert result["clarification"]
    assert result.get("sql") is None
