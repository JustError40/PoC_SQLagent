from sqlagent.db import QueryResult
from sqlagent.verification import verify_skill
from sqlagent.workspace import Workspace


class FakeDatabase:
    def explain(self, query):
        return {"total_cost": 1.0}

    def execute(self, query):
        if "broken" in query:
            raise RuntimeError('relation "broken" does not exist')
        return QueryResult(columns=["n"], rows=[{"n": 1}], elapsed_ms=0.5)


def _workspace_with_templates(tmp_path) -> Workspace:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_text("templates/good.sql", "SELECT 1 AS n;\n")
    workspace.write_text("templates/bad.sql", "SELECT * FROM broken;\n")
    workspace.write_yaml(
        "manifest.yaml",
        {
            "templates": {
                "good": {"path": "templates/good.sql", "description": "works"},
                "bad": {"path": "templates/bad.sql", "description": "fails"},
            }
        },
    )
    return workspace


def test_verify_marks_failing_templates_and_snapshots_results(tmp_path) -> None:
    workspace = _workspace_with_templates(tmp_path)

    report = verify_skill(FakeDatabase(), workspace)

    assert report["checked"] == 2
    assert report["failing"] == ["bad"]
    manifest = workspace.read_yaml("manifest.yaml")
    assert manifest["templates"]["good"]["status"] == "ok"
    assert manifest["templates"]["good"]["result_hash"]
    assert manifest["templates"]["bad"]["status"] == "failing"
    assert "does not exist" in manifest["templates"]["bad"]["last_error"]


def test_verify_detects_result_changes_against_baseline(tmp_path) -> None:
    workspace = _workspace_with_templates(tmp_path)
    verify_skill(FakeDatabase(), workspace)

    class ChangedDatabase(FakeDatabase):
        def execute(self, query):
            return QueryResult(columns=["n"], rows=[{"n": 2}], elapsed_ms=0.5)

    report = verify_skill(ChangedDatabase(), workspace)

    assert report["changed"] == ["good"]
