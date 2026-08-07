from sqlagent.db import QueryResult
from sqlagent.verification import verify_skill
from sqlagent.workspace import Workspace, lint_manifest, normalize_manifest


class FakeDatabase:
    def explain(self, query):
        return {"total_cost": 1.0}

    def execute(self, query):
        return QueryResult(columns=["n"], rows=[{"n": 1}], elapsed_ms=0.5)


def test_normalize_manifest_converts_list_templates() -> None:
    manifest = {
        "templates": [
            {"path": "templates/revenue.sql", "description": "revenue by year"},
            {"path": "templates/returns.sql", "description": "return rate"},
        ]
    }

    normalized = normalize_manifest(manifest)

    templates = normalized["templates"]
    assert set(templates) == {"revenue", "returns"}
    assert templates["revenue"]["path"] == "templates/revenue.sql"
    assert templates["revenue"]["description"] == "revenue by year"


def test_normalize_manifest_keeps_dict_templates() -> None:
    manifest = {"templates": {"good": {"path": "templates/good.sql"}}}

    assert normalize_manifest(manifest)["templates"] == {"good": {"path": "templates/good.sql"}}


def test_normalize_manifest_handles_garbage() -> None:
    assert normalize_manifest(None) == {}
    assert normalize_manifest(["not", "a", "mapping"]) == {}
    assert normalize_manifest({"templates": "oops"})["templates"] == {}


def test_lint_manifest_flags_list_templates() -> None:
    issues = lint_manifest({"templates": [{"path": "templates/a.sql"}]})

    assert any("templates is a list" in issue for issue in issues)


def test_lint_manifest_ok_on_canonical_shape() -> None:
    assert lint_manifest({"templates": {"a": {"path": "templates/a.sql"}}}) == []


def test_verify_survives_list_shaped_manifest(tmp_path) -> None:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_text("templates/good.sql", "SELECT 1 AS n;\n")
    workspace.write_yaml(
        "manifest.yaml",
        {"templates": [{"path": "templates/good.sql", "description": "works"}]},
    )

    report = verify_skill(FakeDatabase(), workspace)

    assert report["checked"] == 1
    assert report["failing"] == []
    manifest = workspace.read_yaml("manifest.yaml")
    assert manifest["templates"]["good"]["status"] == "ok"
