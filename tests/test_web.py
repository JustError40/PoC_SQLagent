from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from sqlagent import web


def test_status_tolerates_list_shaped_manifest(tmp_path, monkeypatch):
    # Legacy/corrupt workspaces may hold a bare YAML list in manifest.yaml;
    # the status endpoint must not 500 on it.
    (tmp_path / "manifest.yaml").write_text('["web_sales_by_state_revenue.sql"]\n', encoding="utf-8")
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, workspace_path=tmp_path))

    response = TestClient(web.app).get("/api/status")

    assert response.status_code == 200
    assert response.json()["workspace"]["templates_count"] == 0
