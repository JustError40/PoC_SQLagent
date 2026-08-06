from sqlagent.db import QueryResult
from sqlagent.query_agent.graph import QueryAgent, metadata_drift
from sqlagent.workspace import Workspace


def test_metadata_drift_flags_catalog_sql_for_business_question() -> None:
    assert metadata_drift(
        "какие штаты принесли больше всего интернет-выручки",
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'store_returns'",
    )


def test_metadata_drift_allows_catalog_sql_for_meta_question() -> None:
    assert not metadata_drift(
        "сколько колонок в таблице store_returns",
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'store_returns'",
    )


def test_metadata_drift_ignores_plain_business_sql() -> None:
    assert not metadata_drift("выручка по штатам", "SELECT state, sum(net) FROM web_sales GROUP BY 1")


class FakeCriticLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat_json(self, system, user, schema=None):
        self.calls.append(system)
        if "You generate one PostgreSQL SELECT" in system:
            return {"sql": "SELECT 'store_returns' AS table_name, COUNT(*) AS column_count FROM information_schema.columns WHERE table_name = 'store_returns'"}
        if "bounded ReAct SQL repair agent" in system:
            return {"sql": "SELECT ca_state, SUM(ws_net_paid) AS internet_revenue FROM web_sales ws JOIN customer_address ca ON ws.ws_bill_addr_sk = ca.ca_address_sk GROUP BY ca_state ORDER BY internet_revenue DESC", "rationale": "answer with business data"}
        if "You verify that a SQL query" in system:
            return {"answered": True, "feedback": ""}
        raise AssertionError(f"unexpected LLM call: {system[:60]}")


class FakeDatabase:
    def explain(self, query):
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        return QueryResult(columns=["ca_state"], rows=[{"ca_state": "CA"}], elapsed_ms=0.2)


def test_critic_rejects_metadata_drift_and_repair_answers_with_data(tmp_path) -> None:
    llm = FakeCriticLLM()
    result = QueryAgent(FakeDatabase(), Workspace(tmp_path / "skill"), llm).run(
        "какие штаты принесли больше всего интернет-выручки"
    )

    assert not result.get("error")
    assert "ws_net_paid" in result["sql"]
    assert result["react_attempts"] == 1
    assert result["critic"] == {"answered": True, "feedback": ""}
    assert not any("You verify that a SQL query" in call for call in llm.calls[:1])  # drift caught deterministically first
