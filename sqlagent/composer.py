"""Structured query composition for small models.

Asking a small model for a complete SQL string invites hallucinated syntax and
identifiers. Instead the model fills a small JSON query plan (a decomposer
subagent), and this module — a deterministic assembler — turns the plan into
SQL. Syntax can no longer be invented; every identifier is validated against
the surveyed schema, and assembly errors are precise observations that the
ReAct repair loop can fix part by part.
"""

from __future__ import annotations

import re
from typing import Any

AGGREGATIONS = {"sum", "avg", "min", "max", "count", "count_distinct"}
FILTER_OPS = {"=", "!=", ">", ">=", "<", "<="}
MAX_JOINS = 4
MAX_MEASURES = 4

DECOMPOSE_PROMPT = (
    "You plan one analytical PostgreSQL query as JSON parts instead of writing SQL. "
    "Pick tables and columns only from the supplied schema map — never invent identifiers. "
    "Return JSON with: "
    '"from": main table; '
    '"joins": [{"table", "left", "right"}] where left is a column of an already used table and '
    "right is a column of the joined table (max 4, empty list when not needed); "
    '"group_by": [{"table", "column"}] for the entities the question asks about; '
    '"measures": [{"agg": one of sum|avg|min|max|count|count_distinct, "table", "column", "alias"}] '
    "— one to four measures; questions like 'revenue and profit' or 'average basket' need several; "
    '"filters": [{"table", "column", "op": one of =|!=|>|>=|<|<=, "value"}] (empty list when not needed); '
    '"order": {"by": a measure alias or a group column, "dir": asc|desc}; '
    'Optional "limit": number only when the user explicitly asks for top/bottom N; otherwise omit it. '
    "UI preview limits are applied outside SQL and must not change the analytical result. Use empty lists where nothing is needed. "
    'If a table you need is missing from the supplied schema map, return '
    '{"needed_tables": [exact table names you want to see]} instead of a plan.'
)

SPEC_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "joins": {"type": "array"},
        "group_by": {"type": "array"},
        "measure": {"type": "object"},
        "measures": {"type": "array"},
        "filters": {"type": "array"},
        "order": {"type": "object"},
        "limit": {"type": "integer"},
    },
    "required": ["from"],
}


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _quote_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _check_table(schema: dict[str, list[str]], table: str) -> None:
    if table not in schema:
        raise ValueError(f"unknown table: {table or '(missing)'}")


def _check_column(schema: dict[str, list[str]], table: str, column: str) -> None:
    _check_table(schema, table)
    if column != "*" and column not in schema[table]:
        raise ValueError(f"unknown column: {table}.{column}")


def _owner_of(schema: dict[str, list[str]], known_tables: set[str], column: str) -> str | None:
    for table in sorted(known_tables):
        if column in schema.get(table, []):
            return table
    return None


def _join_sides(join: dict[str, Any]) -> tuple[str, str]:
    """Extract (left, right) join columns, tolerating a model's 'join'/'on' spelling."""

    left, right = str(join.get("left") or ""), str(join.get("right") or "")
    if left and right:
        return left, right
    expr = join.get("join", join.get("on", ""))
    if isinstance(expr, list):
        expr = expr[0] if expr else ""
    sides = re.split(r"\s*=\s*", str(expr), maxsplit=1)
    if len(sides) == 2 and all(sides):
        return sides[0].split(".")[-1], sides[1].split(".")[-1]
    return left, right


def assemble_spec(
    spec: dict[str, Any],
    schema: dict[str, list[str]],
    *,
    default_limit: int | None = None,
    max_limit: int | None = None,
) -> str:
    """Build one read-only SELECT from a validated query plan; raise ValueError on any bad part."""

    if not isinstance(spec, dict):
        raise ValueError("query plan is not an object")
    base = str(spec.get("from") or "")
    _check_table(schema, base)
    known = {base}

    join_clauses: list[str] = []
    joins = spec.get("joins") or []
    if len(joins) > MAX_JOINS:
        raise ValueError(f"too many joins (max {MAX_JOINS})")
    for join in joins:
        if not isinstance(join, dict):
            raise ValueError("join is not an object")
        table = str(join.get("table") or "")
        left, right = _join_sides(join)
        _check_table(schema, table)
        left_table = _owner_of(schema, known, left)
        if left_table is None:
            raise ValueError(f"unknown join column: {left or join!r}")
        _check_column(schema, table, right)
        join_clauses.append(f"JOIN {_quote_ident(table)} ON {_quote_ident(left_table)}.{_quote_ident(left)} = {_quote_ident(table)}.{_quote_ident(right)}")
        known.add(table)

    select_parts: list[str] = []
    group_exprs: list[str] = []
    group_columns: list[str] = []
    for dim in spec.get("group_by") or []:
        if not isinstance(dim, dict):
            raise ValueError("group_by entry is not an object")
        table = str(dim.get("table") or base)
        column = str(dim.get("column") or "")
        if table not in known:
            raise ValueError(f"group_by table not joined: {table}")
        _check_column(schema, table, column)
        select_parts.append(f"{_quote_ident(table)}.{_quote_ident(column)} AS {_quote_ident(column)}")
        group_exprs.append(f"{_quote_ident(table)}.{_quote_ident(column)}")
        group_columns.append(column)

    measure_aliases: list[str] = []
    measures = spec.get("measures")
    if not measures and spec.get("measure"):
        measures = [spec["measure"]]
    measures = measures or []
    if len(measures) > MAX_MEASURES:
        raise ValueError(f"too many measures (max {MAX_MEASURES})")
    for measure in measures:
        if not isinstance(measure, dict):
            raise ValueError("measure is not an object")
        agg = str(measure.get("agg") or "count").lower()
        if agg not in AGGREGATIONS:
            raise ValueError(f"unsupported aggregation: {agg}")
        column = str(measure.get("column") or "*")
        table = str(measure.get("table") or base)
        if table not in known:
            raise ValueError(f"measure table not joined: {table}")
        _check_column(schema, table, column)
        measure_alias = re.sub(r"\W+", "_", str(measure.get("alias") or f"{agg}_{column}")).strip("_") or "measure"
        if measure_alias in measure_aliases:
            raise ValueError(f"duplicate measure alias: {measure_alias}")
        if agg == "count" and column == "*":
            expression = "COUNT(*)"
        elif agg == "count_distinct":
            expression = f"COUNT(DISTINCT {_quote_ident(table)}.{_quote_ident(column)})"
        else:
            expression = f"{agg.upper()}({_quote_ident(table)}.{_quote_ident(column)})"
        select_parts.append(f"{expression} AS {_quote_ident(measure_alias)}")
        measure_aliases.append(measure_alias)
    if not select_parts:
        raise ValueError("query plan selects nothing: add group_by or a measure")

    where_parts: list[str] = []
    for filt in spec.get("filters") or []:
        if not isinstance(filt, dict):
            raise ValueError("filter is not an object")
        table = str(filt.get("table") or base)
        column = str(filt.get("column") or "")
        op = str(filt.get("op") or "=").strip()
        if table not in known:
            raise ValueError(f"filter table not joined: {table}")
        _check_column(schema, table, column)
        if op not in FILTER_OPS:
            raise ValueError(f"unsupported filter operator: {op}")
        where_parts.append(f"{_quote_ident(table)}.{_quote_ident(column)} {op} {_quote_literal(filt.get('value'))}")

    order_clause = ""
    order = spec.get("order")
    if isinstance(order, dict) and order.get("by"):
        by = str(order["by"])
        if by == "measure" and measure_aliases:
            by = measure_aliases[0]
        if by not in group_columns and by not in measure_aliases:
            raise ValueError(f"order column is not selected: {by}")
        direction = "DESC" if str(order.get("dir") or "desc").lower() == "desc" else "ASC"
        order_clause = f" ORDER BY {_quote_ident(by)} {direction}"

    raw_limit = spec.get("limit", default_limit)
    limit: int | None = None
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be a positive integer") from exc
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        if max_limit is not None:
            limit = min(limit, max_limit)

    query = f"SELECT {', '.join(select_parts)} FROM {_quote_ident(base)}"
    if join_clauses:
        query += " " + " ".join(join_clauses)
    if where_parts:
        query += " WHERE " + " AND ".join(where_parts)
    if group_exprs:
        query += " GROUP BY " + ", ".join(group_exprs)
    query += order_clause
    if limit is not None:
        query += f" LIMIT {limit}"
    return query
