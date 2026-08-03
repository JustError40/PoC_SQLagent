from sqlagent.db import QueryResult
from sqlagent.query_agent.graph import QueryAgent
from sqlagent.workspace import Workspace


class FakeRepairLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, system, user, schema=None):
        self.calls += 1
        if self.calls == 1:
            return {"sql": 'SELECT * FROM returns WHERE inventory_snapshots = true'}
        return {"sql": "SELECT * FROM returns LIMIT 1", "rationale": "removed an unknown column using schema context"}


class FakeDatabase:
    def __init__(self) -> None:
        self.explain_calls = 0

    def explain(self, query):
        self.explain_calls += 1
        if "inventory_snapshots" in query:
            raise RuntimeError('column "inventory_snapshots" does not exist')
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        return QueryResult(columns=["id"], rows=[{"id": 1}], elapsed_ms=0.2)


def test_react_repairs_explain_error_and_rechecks_query(tmp_path) -> None:
    database = FakeDatabase()
    llm = FakeRepairLLM()
    result = QueryAgent(database, Workspace(tmp_path / "skill"), llm).run("покажи возвраты")

    assert not result.get("error")
    assert result["sql"] == "SELECT * FROM returns LIMIT 1"
    assert result["react_attempts"] == 1
    assert result["react_steps"][0]["phase"] == "observe"
    assert result["react_steps"][1]["action"] == "repair_sql"
    assert database.explain_calls == 2
