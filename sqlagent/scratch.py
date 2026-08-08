from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
import psycopg

from sqlagent.concurrency import AdaptiveLimiter, POSTGRES_LIMITER
from sqlagent.db import QueryResult, json_safe, validate_read_only
from sqlagent.telemetry import span


class ScratchLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScratchLimits:
    max_rows: int = 1_000_000
    max_bytes: int = 512 * 1024 * 1024
    timeout_ms: int = 120_000


class ScratchExecutor:
    """Run controlled multi-stage SQL on one pinned connection using pg_temp."""

    def __init__(
        self,
        dsn: str,
        limits: ScratchLimits | None = None,
        preview_rows: int = 500,
        limiter: AdaptiveLimiter | None = POSTGRES_LIMITER,
        priority: int = 0,
    ) -> None:
        self.dsn = dsn
        self.limits = limits or ScratchLimits()
        self.preview_rows = preview_rows
        self.limiter = limiter
        self.priority = priority

    @staticmethod
    def _name(request_id: str, index: int) -> str:
        digest = hashlib.sha256(f"{request_id}:{index}".encode()).hexdigest()[:12]
        return f"sqlagent_{index}_{digest}"

    def execute(self, request_id: str, stages: list[str], final_sql: str) -> QueryResult:
        if not stages:
            raise ValueError("scratch execution requires at least one materialized stage")
        started = time.perf_counter()
        from contextlib import nullcontext

        limited = self.limiter.slot(priority=self.priority) if self.limiter else nullcontext()
        with limited, span("db", "scratch_execute", stages=len(stages)):
            with psycopg.connect(self.dsn) as conn:
                conn.execute("SET default_transaction_read_only = on")
                conn.execute(f"SET LOCAL statement_timeout = {int(self.limits.timeout_ms)}")
                names: list[str] = []
                for index, stage_sql in enumerate(stages, 1):
                    expanded = stage_sql
                    for previous, previous_name in enumerate(names, 1):
                        expanded = expanded.replace(f"{{{{stage_{previous}}}}}", f'pg_temp."{previous_name}"')
                    query = validate_read_only(expanded)
                    name = self._name(request_id, index)
                    conn.execute(
                        f'CREATE TEMP TABLE "{name}" ON COMMIT DROP AS '
                        f'SELECT * FROM ({query}) AS bounded_stage LIMIT {self.limits.max_rows + 1}'
                    )
                    rows = conn.execute(f'SELECT count(*) FROM pg_temp."{name}"').fetchone()[0]
                    size = conn.execute(
                        "SELECT pg_total_relation_size(oid) FROM pg_class WHERE oid = %s::regclass",
                        (f"pg_temp.{name}",),
                    ).fetchone()[0]
                    if int(rows) > self.limits.max_rows:
                        raise ScratchLimitError(f"scratch row limit exceeded: {rows} > {self.limits.max_rows}")
                    if int(size) > self.limits.max_bytes:
                        raise ScratchLimitError(f"scratch byte limit exceeded: {size} > {self.limits.max_bytes}")
                    names.append(name)
                expanded_final = final_sql
                for previous, previous_name in enumerate(names, 1):
                    expanded_final = expanded_final.replace(
                        f"{{{{stage_{previous}}}}}", f'pg_temp."{previous_name}"'
                    )
                query = validate_read_only(expanded_final)
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    columns = [item.name for item in cursor.description or []]
                    values = cursor.fetchmany(self.preview_rows + 1)
                # The context commits, ON COMMIT DROP removes every generated table.
        rows = [dict(zip(columns, value)) for value in values[: self.preview_rows]]
        return QueryResult(
            columns=columns,
            rows=json_safe(rows),
            elapsed_ms=(time.perf_counter() - started) * 1000,
            truncated=len(values) > self.preview_rows,
        )
