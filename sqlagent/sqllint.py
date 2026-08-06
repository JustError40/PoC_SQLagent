"""Local SQL lint: catch hallucinated identifiers before touching the database.

Uses sqlglot to parse the query and qualify it against the skill's known schema,
so unknown tables/columns become instant, zero-cost observations for the agent
instead of failed round-trips to PostgreSQL.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify


def lint_sql(sql_text: str, schema: dict[str, list[str]]) -> list[str]:
    """Return a list of problems found in sql_text; empty list means the query is clean.

    schema maps table name -> column names (exactly as surveyed from the database).
    """

SYSTEM_SCHEMAS = {"information_schema", "pg_catalog"}


def lint_sql(sql_text: str, schema: dict[str, list[str]]) -> list[str]:
    """Return a list of problems found in sql_text; empty list means the query is clean.

    schema maps table name -> column names (exactly as surveyed from the database).
    System catalogs (information_schema, pg_catalog) are not in the skill schema;
    they are left for the database itself to validate.
    """

    problems: list[str] = []
    try:
        expression = sqlglot.parse_one(sql_text, read="postgres")
    except Exception as exc:
        return [f"SQL parse error: {exc}"]
    if expression is None:
        return ["SQL parse error: empty statement"]

    uses_system_catalog = False
    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        if (table.db or "").lower() in SYSTEM_SCHEMAS:
            uses_system_catalog = True
            continue
        if name and name not in schema and not _inside_cte(expression, name):
            problems.append(f"unknown table: {table.name}")
    if problems or uses_system_catalog:
        return problems

    typed_schema = {table: {column: "UNKNOWN" for column in columns} for table, columns in schema.items()}
    try:
        qualify(
            expression.copy(),
            schema=typed_schema,
            dialect="postgres",
            validate_qualify_columns=True,
            infer_schema=False,
        )
    except Exception as exc:
        problems.append(f"identifier error: {str(exc).splitlines()[0]}")
    return problems


def _inside_cte(expression: exp.Expression, name: str) -> bool:
    return any(cte.alias_or_name.lower() == name for cte in expression.find_all(exp.CTE))


def schema_from_tables_yaml(tables: list[dict]) -> dict[str, list[str]]:
    """Build the lint schema from schema/tables.yaml content."""

    return {
        str(table["name"]).lower(): [str(column["column_name"]) for column in table.get("columns", [])]
        for table in tables
        if isinstance(table, dict) and table.get("name")
    }
