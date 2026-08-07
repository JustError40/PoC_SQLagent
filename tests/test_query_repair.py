from sqlagent.db import QueryResult
from sqlagent.query_agent.graph import QueryAgent, _clean_sql
from sqlagent.workspace import Workspace


def test_clean_sql_extracts_statement_from_prose() -> None:
    assert _clean_sql("Here is the query:\nSELECT 1;\nHope it helps") == "SELECT 1;"
    assert _clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert _clean_sql("WITH x AS (SELECT 1) SELECT * FROM x;") == "WITH x AS (SELECT 1) SELECT * FROM x;"


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


class EchoThenFixLLM:
    """Repair first echoes the broken SQL, then proposes a real fix."""

    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, system, user, schema=None):
        self.calls += 1
        if self.calls == 1:
            return {"sql": "SELECT bad_col FROM returns"}
        if self.calls == 2:
            return {"sql": "SELECT bad_col FROM returns", "rationale": "echo"}
        if self.calls == 3:
            return {"sql": "SELECT * FROM returns LIMIT 1", "rationale": "dropped the unknown column"}
        return {"answered": True, "feedback": ""}


class BadColumnDatabase:
    def explain(self, query):
        if "bad_col" in query:
            raise RuntimeError('column "bad_col" does not exist')
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        return QueryResult(columns=["id"], rows=[{"id": 1}], elapsed_ms=0.2)


def test_react_retries_when_repair_echoes_the_same_sql(tmp_path) -> None:
    result = QueryAgent(BadColumnDatabase(), Workspace(tmp_path / "skill"), EchoThenFixLLM()).run("покажи возвраты")

    assert not result.get("error")
    assert result["sql"] == "SELECT * FROM returns LIMIT 1"
    assert result["react_attempts"] == 2
    phases = [(step["attempt"], step["phase"]) for step in result["react_steps"]]
    assert (1, "observe") in phases and (2, "act") in phases


class SlowThenFastDatabase:
    def execute(self, query):
        elapsed = 50_000.0 if "ORDER BY 1" in query else 200.0
        return QueryResult(columns=["id"], rows=[{"id": 1}], elapsed_ms=elapsed)

    def explain(self, query):
        return {"plan": {"Plan": {"Node Type": "Aggregate", "Plan Rows": 1, "Actual Rows": 1}},
                "total_cost": 1.0, "actual_ms": 0.1, "rows": 1}


class OptimizerLLM:
    def chat_json(self, system, user, schema=None):
        if "optimize a correct PostgreSQL query" in system:
            return {"sql": "SELECT * FROM returns", "rationale": "drop useless sort"}
        if "verify that a SQL query" in system:
            return {"answered": True, "feedback": ""}
        return {"sql": "SELECT * FROM returns ORDER BY 1"}


def test_optimizer_rewrites_slow_query_and_adopts_faster_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("sqlagent.query_agent.graph.REACT_OPTIMIZE_MS", 1000.0)

    result = QueryAgent(SlowThenFastDatabase(), Workspace(tmp_path / "skill"), OptimizerLLM()).run("покажи возвраты")

    assert not result.get("error")
    assert result["sql"] == "SELECT * FROM returns"
    assert result["result"]["elapsed_ms"] == 200.0
    actions = [step.get("action") for step in result["react_steps"]]
    assert "optimize_adopted" in actions


def test_optimizer_keeps_original_when_rewrite_is_slower(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("sqlagent.query_agent.graph.REACT_OPTIMIZE_MS", 1000.0)

    class SlowerRewriteLLM(OptimizerLLM):
        def chat_json(self, system, user, schema=None):
            if "optimize a correct PostgreSQL query" in system:
                return {"sql": "SELECT * FROM returns ORDER BY 1", "rationale": "no idea"}
            return super().chat_json(system, user, schema)

    result = QueryAgent(SlowThenFastDatabase(), Workspace(tmp_path / "skill"), SlowerRewriteLLM()).run("покажи возвраты")

    assert not result.get("error")
    assert result["result"]["elapsed_ms"] == 50_000.0
    assert "optimize_adopted" not in [step.get("action") for step in result["react_steps"]]
