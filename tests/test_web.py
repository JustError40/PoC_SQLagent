from __future__ import annotations

import dataclasses
import asyncio
import time

from sqlagent import web
from sqlagent.workspace import Workspace


def test_status_tolerates_list_shaped_manifest(tmp_path, monkeypatch):
    # Legacy/corrupt workspaces may hold a bare YAML list in manifest.yaml;
    # the status endpoint must not 500 on it.
    (tmp_path / "manifest.yaml").write_text('["web_sales_by_state_revenue.sql"]\n', encoding="utf-8")
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, workspace_path=tmp_path))

    payload = asyncio.run(web.status())

    assert payload["workspace"]["templates_count"] == 0


def test_promote_without_candidate_completes_as_skipped(tmp_path, monkeypatch):
    # Evolve may legitimately produce no candidate (no trajectories, infra
    # incident, or everything already merged) — promote must be a no-op then.
    workspace = Workspace(tmp_path / "skill")
    workspace.write_text("SKILL.md", "skill\n")
    workspace.commit("init")
    monkeypatch.setattr(web, "runtime", lambda *args, **kwargs: (object(), workspace, None))

    started = web.promote_endpoint()

    job = web.jobs.get(started["job_id"])
    deadline = time.monotonic() + 10
    while job and job["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        job = web.jobs.get(started["job_id"])
    assert job is not None
    assert job["status"] == "completed"
    assert job["result"]["status"] == "skipped"
