import json

from sqlagent.db import QueryResult
from sqlagent.explorer import run_exploration
from sqlagent.workspace import Workspace


class FakeExplorerLLM:
    def __init__(self) -> None:
        self.plan_calls = 0

    def chat_json(self, system, user, schema=None):
        if "exploring a PostgreSQL database" in system:
            self.plan_calls += 1
            return {
                "probes": [
                    {"name": "monthly_revenue", "question": "revenue by month", "sql": "SELECT 1 AS revenue"},
                    {"name": "extra_probe", "question": "over budget", "sql": "SELECT 2 AS extra"},
                ]
            }
        if "Reflect on your own work" in system:
            return {"lessons": ["always copy identifiers verbatim from the schema"], "note": "round reviewed"}
        return {
            "artifacts": [
                {
                    "type": "template",
                    "name": "monthly_revenue",
                    "description": "revenue by month",
                    "grain": "one row per month",
                    "sql": "SELECT 1 AS revenue",
                },
                {"type": "template", "name": "unsafe", "sql": "DELETE FROM orders"},  # not read-only: must be rejected
                {"type": "rule", "rule": "always filter soft-deleted rows"},
            ]
        }


class FakeDatabase:
    def explain(self, query):
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        return QueryResult(columns=["revenue"], rows=[{"revenue": 1}], elapsed_ms=0.2)


def _workspace(tmp_path) -> Workspace:
    workspace = Workspace(tmp_path / "skill")
    workspace.ensure_git()
    workspace.write_yaml("manifest.yaml", {"version": 1, "tables": ["orders"], "domains": {"all": ["orders"]}, "templates": {}})
    workspace.write_yaml("relationships/dangerous_joins.yaml", {"joins": []})
    workspace.commit("init")
    return workspace


def test_explorer_writes_verified_template_and_rule(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    result = run_exploration(FakeDatabase(), workspace, FakeExplorerLLM(), rounds=1, probes_per_round=2)

    assert "templates/monthly_revenue.sql" in result["written"]
    assert "relationships/learned_rules.yaml" in result["written"]
    assert (workspace.root / "templates" / "monthly_revenue.sql").exists()
    manifest = workspace.read_yaml("manifest.yaml")
    assert manifest["templates"]["monthly_revenue"]["grain"] == "one row per month"
    # the unsafe template must not be promoted into the skill
    assert not (workspace.root / "templates" / "unsafe.sql").exists()
    log = (workspace.root / "experience" / "exploration.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log) == 2
    assert json.loads(log[0])["status"] == "ok"


def test_explorer_respects_probe_budget(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run_exploration(FakeDatabase(), workspace, FakeExplorerLLM(), rounds=1, probes_per_round=1)

    log = (workspace.root / "experience" / "exploration.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1


class FlakyDatabase:
    def explain(self, query):
        if "no_such_column" in query:
            raise RuntimeError('column "no_such_column" does not exist')
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}

    def execute(self, query):
        return QueryResult(columns=["revenue"], rows=[{"revenue": 1}], elapsed_ms=0.2)


class RepairingExplorerLLM:
    def chat_json(self, system, user, schema=None):
        if "exploring a PostgreSQL database" in system:
            return {"probes": [{"name": "bad_probe", "question": "q", "sql": "SELECT no_such_column FROM orders"}]}
        if "failed. Fix the SQL" in system:
            return {"sql": "SELECT 1 AS revenue"}
        if "Reflect on your own work" in system:
            return {"lessons": ["check unknown columns against the schema first"], "note": "learned"}
        return {"artifacts": [{"type": "template", "name": "repaired_metric", "description": "d", "grain": "g", "sql": "SELECT 1 AS revenue"}]}


def test_explorer_repairs_failed_probe_and_keeps_template(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    result = run_exploration(FlakyDatabase(), workspace, RepairingExplorerLLM(), rounds=1, probes_per_round=1)

    assert "templates/repaired_metric.sql" in result["written"]
    log = [json.loads(line) for line in (workspace.root / "experience" / "exploration.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[0]["status"] == "ok"
    assert log[0]["repaired"] is True


def test_self_reflection_writes_lessons_into_skill(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    run_exploration(FakeDatabase(), workspace, FakeExplorerLLM(), rounds=1, probes_per_round=1)

    reflections = (workspace.root / "experience" / "reflections.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(reflections) == 1
    assert json.loads(reflections[0])["lessons"] == ["always copy identifiers verbatim from the schema"]
    skill = (workspace.root / "SKILL.md").read_text(encoding="utf-8")
    assert "## Lessons from exploration" in skill
    assert "always copy identifiers verbatim from the schema" in skill


class CountingDatabase(FakeDatabase):
    def __init__(self) -> None:
        self.explained: list[str] = []

    def explain(self, query):
        self.explained.append(query)
        return {"total_cost": 1.0, "actual_ms": 0.1, "rows": 1}


class LintBlockedLLM:
    def chat_json(self, system, user, schema=None):
        if "exploring a PostgreSQL database" in system:
            return {"probes": [{"name": "bad_table", "question": "q", "sql": "SELECT * FROM web_sales LIMIT 1"}]}
        if "failed. Fix the SQL" in system:
            return {"sql": "SELECT count(*) AS n FROM orders"}
        if "Reflect on your own work" in system:
            return {"lessons": [], "note": ""}
        return {"artifacts": []}


def test_lint_blocks_unknown_tables_before_the_database(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    workspace.write_yaml(
        "schema/tables.yaml",
        {"tables": [{"name": "orders", "columns": [{"column_name": "id"}]}]},
    )
    database = CountingDatabase()
    run_exploration(database, workspace, LintBlockedLLM(), rounds=1, probes_per_round=1)

    assert all("web_sales" not in query for query in database.explained)  # lint stopped it pre-DB
    log = [json.loads(line) for line in (workspace.root / "experience" / "exploration.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[0]["status"] == "ok"  # repaired via lint error feedback
    assert log[0]["repaired"] is True


def test_explorer_stops_cleanly_without_llm(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    result = run_exploration(FakeDatabase(), workspace, None, rounds=3)

    assert result["rounds_run"] == 0
    assert result["stop_reason"] == "llm_unavailable"
    assert result["written"] == []
