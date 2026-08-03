from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Iterable

import psycopg
import sqlparse


class QuerySafetyError(ValueError):
    """Raised when generated SQL is not a read-only query."""


DatabaseEventHook = Callable[[str, str], None]


FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|UPSERT|MERGE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|COPY|CALL|DO)\b",
    re.IGNORECASE,
)
DEFAULT_FORBIDDEN_TABLES = {"pg_authid", "pg_shadow", "information_schema.sql_features"}


def validate_read_only(sql: str, forbidden_tables: Iterable[str] = ()) -> str:
    query = sqlparse.format(sql.strip(), strip_comments=True).strip().rstrip(";").strip()
    if not query:
        raise QuerySafetyError("empty SQL")
    statements = [statement for statement in sqlparse.parse(query) if statement.tokens]
    if len(statements) != 1:
        raise QuerySafetyError("exactly one SQL statement is required")
    lowered = query.lower()
    if FORBIDDEN_KEYWORDS.search(query):
        raise QuerySafetyError("only read-only SELECT statements are allowed")
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise QuerySafetyError("query must start with SELECT or WITH")
    blocked = set(DEFAULT_FORBIDDEN_TABLES) | {table.lower() for table in forbidden_tables}
    for table in blocked:
        if re.search(rf"\b{re.escape(table)}\b", lowered):
            raise QuerySafetyError(f"forbidden table referenced: {table}")
    return query


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return value


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    elapsed_ms: float
    truncated: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": json_safe(self.rows),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "truncated": self.truncated,
        }


class Database:
    def __init__(
        self,
        dsn: str,
        max_rows: int = 500,
        statement_timeout_ms: int = 15_000,
        event_hook: DatabaseEventHook | None = None,
    ) -> None:
        self.dsn = dsn
        self.max_rows = max_rows
        self.statement_timeout_ms = statement_timeout_ms
        self.event_hook = event_hook

    def _emit(self, event: str, detail: str) -> None:
        if self.event_hook:
            self.event_hook(event, detail)

    def _connection(self) -> psycopg.Connection:
        try:
            conn = psycopg.connect(self.dsn)
            conn.execute("SET default_transaction_read_only = on")
            conn.execute(f"SET statement_timeout = {int(self.statement_timeout_ms)}")
            self._emit("connected", self.dsn.rsplit("/", 1)[-1])
            return conn
        except Exception as exc:
            self._emit("error", str(exc))
            raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        query = validate_read_only(sql)
        started = time.perf_counter()
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                columns = [description.name for description in cursor.description or []]
                rows = [dict(zip(columns, row)) for row in cursor.fetchmany(self.max_rows + 1)]
        return QueryResult(
            columns=columns,
            rows=json_safe(rows[: self.max_rows]),
            elapsed_ms=(time.perf_counter() - started) * 1000,
            truncated=len(rows) > self.max_rows,
        )

    def explain(self, sql: str) -> dict[str, Any]:
        query = validate_read_only(sql)
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS, TIMING false) {query}")
                payload = cursor.fetchone()[0]
        plan = payload[0] if isinstance(payload, list) else payload
        return {
            "plan": plan,
            "total_cost": float(plan.get("Plan", {}).get("Total Cost", 0)),
            "actual_ms": float(plan.get("Execution Time", 0)),
            "rows": int(plan.get("Plan", {}).get("Actual Rows", 0)),
        }

    def table_inventory(self) -> list[dict[str, Any]]:
        query = """
        SELECT table_schema, table_name,
               c.reltuples::bigint AS estimated_rows,
               pg_total_relation_size(format('%I.%I', table_schema, table_name)) AS bytes
        FROM information_schema.tables t
        JOIN pg_class c ON c.relname = t.table_name
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(query).fetchall()
            columns = [description.name for description in conn.execute(query).description]
        return [json_safe(dict(zip(columns, row))) for row in rows]
