from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


INFRA_ERROR_TYPES = {
    "llm_timeout",
    "llm_transport_error",
    "explain_timeout",
    "execution_timeout",
    "db_error",
    "serialization_failed",
}


@dataclass(frozen=True)
class FailureJob:
    id: str
    request_id: str
    fingerprint: str
    error_type: str
    surface: str | None
    status: str
    occurrence_count: int
    payload: dict[str, Any]


def failure_fingerprint(error_type: str, stage: str, message: str) -> str:
    normalized = " ".join(message.lower().split())[:500]
    return hashlib.sha256(f"{error_type}\0{stage}\0{normalized}".encode()).hexdigest()


class FailureQueue:
    """Run-local durable queue. SQLite WAL allows one learner and many request writers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS failure_jobs (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    surface TEXT,
                    status TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    result_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_active_failure
                ON failure_jobs(fingerprint)
                WHERE status IN ('pending', 'running');
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    def enqueue(
        self,
        *,
        request_id: str,
        error_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
        surface: str | None = None,
    ) -> str:
        fingerprint = failure_fingerprint(error_type, stage, message)
        now = time.time()
        document = {"stage": stage, "message": message, **(payload or {})}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT id FROM failure_jobs WHERE fingerprint = ? AND status IN ('pending', 'running')",
                (fingerprint,),
            ).fetchone()
            if active:
                conn.execute(
                    "UPDATE failure_jobs SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ?",
                    (now, active["id"]),
                )
                conn.commit()
                return str(active["id"])
            job_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO failure_jobs VALUES (?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?, NULL)",
                (job_id, request_id, fingerprint, error_type, surface, json.dumps(document, default=str), now, now),
            )
            if error_type in INFRA_ERROR_TYPES:
                conn.execute(
                    "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, request_id, fingerprint, error_type, json.dumps(document, default=str), now),
                )
                conn.execute(
                    "UPDATE failure_jobs SET status = 'incident', updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
            conn.commit()
            return job_id

    def claim(self) -> FailureJob | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM failure_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                "UPDATE failure_jobs SET status = 'running', updated_at = ? WHERE id = ?",
                (time.time(), row["id"]),
            )
            conn.commit()
            return FailureJob(
                id=row["id"],
                request_id=row["request_id"],
                fingerprint=row["fingerprint"],
                error_type=row["error_type"],
                surface=row["surface"],
                status="running",
                occurrence_count=row["occurrence_count"],
                payload=json.loads(row["payload_json"]),
            )

    def finish(self, job_id: str, status: str, result: dict[str, Any]) -> None:
        if status not in {"completed", "rejected", "failed"}:
            raise ValueError("invalid terminal failure-job status")
        with self._connect() as conn:
            conn.execute(
                "UPDATE failure_jobs SET status = ?, result_json = ?, updated_at = ? WHERE id = ?",
                (status, json.dumps(result, default=str), time.time(), job_id),
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM failure_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


class LearnerWorker:
    """Exactly one background learner loop per process."""

    def __init__(self, queue: FailureQueue, handler: Callable[[FailureJob], dict[str, Any]]) -> None:
        self.queue = queue
        self.handler = handler
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sqlagent-background-learner", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self.queue.claim()
            if job is None:
                self._stop.wait(0.25)
                continue
            try:
                result = self.handler(job)
                status = "completed" if result.get("status") == "promoted" else "rejected"
            except Exception as exc:
                result, status = {"error": str(exc)}, "failed"
            self.queue.finish(job.id, status, result)
