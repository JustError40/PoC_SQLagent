"""Periodic revalidation of the skill's executable knowledge.

Templates are learned artifacts: the database can change under them, and a
template that once ran cleanly can start failing or return different data.
``verify_skill`` re-executes every template through the same read-only gates,
records health and a result snapshot into the manifest, and marks failing
templates so the query agent stops routing questions to them and falls back
to another template or to fresh SQL generation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlagent.db import Database, validate_read_only
from sqlagent.trajectories import append_trajectory
from sqlagent.workspace import Workspace


def _result_hash(rows: list[dict[str, Any]]) -> str:
    normalized = sorted(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows)
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]


def verify_skill(db: Database, workspace: Workspace) -> dict[str, Any]:
    """Re-execute all manifest templates and record their health into the manifest."""

    manifest = workspace.read_manifest()
    templates: dict[str, Any] = manifest.get("templates") or {}
    now = datetime.now(timezone.utc).isoformat()
    report_entries: list[dict[str, Any]] = []
    for name, meta in templates.items():
        entry = dict(meta)
        record: dict[str, Any] = {"template": name}
        path = workspace.root / str(meta.get("path") or "")
        sql_text = path.read_text(encoding="utf-8") if path.exists() else ""
        try:
            if not sql_text.strip():
                raise ValueError("template file missing or empty")
            query = validate_read_only(sql_text)
            db.explain(query)
            result = db.execute(query)
        except Exception as exc:  # a failing template is a finding, not a crash
            entry["status"] = "failing"
            entry["last_error"] = str(exc)[:300]
            record.update({"status": "failing", "error": entry["last_error"]})
        else:
            digest = _result_hash(result.rows)
            baseline = entry.get("result_hash")
            entry.update(
                {
                    "status": "ok",
                    "last_error": "",
                    "verified_at": now,
                    "result_hash": digest,
                    "last_rows": len(result.rows),
                    "last_elapsed_ms": result.elapsed_ms,
                }
            )
            record.update(
                {
                    "status": "ok",
                    "rows": len(result.rows),
                    "elapsed_ms": result.elapsed_ms,
                    "changed_since_baseline": bool(baseline and baseline != digest),
                }
            )
        templates[name] = entry
        report_entries.append(record)
    if templates:
        manifest["templates"] = templates
        workspace.write_yaml("manifest.yaml", manifest)
    report = {
        "created_at": now,
        "checked": len(report_entries),
        "failing": [entry["template"] for entry in report_entries if entry["status"] == "failing"],
        "changed": [entry["template"] for entry in report_entries if entry.get("changed_since_baseline")],
        "entries": report_entries,
    }
    append_trajectory(workspace.root / "experience" / "verification.jsonl", report)
    return report
