"""Deterministic golden evaluation cases.

Cases are derived from the surveyed schema by plain code, never by the model,
so the corpus is an independent yardstick: executing ``golden_sql`` against the
live database yields the known-correct answer, and the agent's full pipeline
(router -> generator -> critic) is compared against it row-by-row.
"""

from __future__ import annotations

import json
from typing import Any

from sqlagent.workspace import Workspace

GOLDEN_PATH = "evals/golden.jsonl"


def _split_ref(ref: str) -> tuple[str, str] | None:
    parts = ref.split(".")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None


def generate_golden_cases(
    tables: list[dict[str, Any]],
    joins: list[dict[str, Any]],
    *,
    max_join_cases: int = 10,
) -> list[dict[str, str]]:
    """Build golden cases from surveyed tables and verified joins.

    Every question is answerable by exactly one deterministic query whose
    result the database itself provides, so correctness is decided by data,
    not by another model judgement.
    """

    cases: list[dict[str, str]] = []
    for table in tables:
        name = str(table.get("name") or "")
        columns = [str(c.get("column_name")) for c in table.get("columns", []) if c.get("column_name")]
        if not name or not columns:
            continue
        cases.append(
            {
                "id": f"rowcount_{name}",
                "question": f"Сколько строк в таблице {name}?",
                "golden_sql": f'SELECT COUNT(*) AS row_count FROM "{name}";',
            }
        )
        key_column = columns[0]
        cases.append(
            {
                "id": f"distinct_{name}_{key_column}",
                "question": f"Сколько уникальных значений в колонке {key_column} таблицы {name}?",
                "golden_sql": f'SELECT COUNT(DISTINCT "{key_column}") AS distinct_count FROM "{name}";',
            }
        )
    for join in joins[:max_join_cases]:
        left = _split_ref(str(join.get("left") or ""))
        right = _split_ref(str(join.get("right") or ""))
        if not left or not right:
            continue
        (left_table, left_column), (right_table, right_column) = left, right
        cases.append(
            {
                "id": f"join_{left_table}_{left_column}_{right_table}",
                "question": (
                    f"Сколько строк получается при соединении таблиц {left_table} и {right_table} "
                    f"по условию {left_column} = {right_column}?"
                ),
                "golden_sql": (
                    f'SELECT COUNT(*) AS join_count FROM "{left_table}" '
                    f'JOIN "{right_table}" ON "{left_table}"."{left_column}" = "{right_table}"."{right_column}";'
                ),
            }
        )
    return cases


def write_golden_cases(workspace: Workspace, cases: list[dict[str, str]]) -> str:
    content = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
    workspace.write_text(GOLDEN_PATH, content)
    return GOLDEN_PATH


def rebuild_golden(workspace: Workspace, *, max_join_cases: int = 10) -> dict[str, Any]:
    """Regenerate the golden corpus of a skill workspace from its surveyed schema."""

    tables = (workspace.read_yaml("schema/tables.yaml", default={}) or {}).get("tables", [])
    joins = (workspace.read_yaml("relationships/verified_joins.yaml", default={}) or {}).get("joins", [])
    cases = generate_golden_cases(tables, joins, max_join_cases=max_join_cases)
    path = write_golden_cases(workspace, cases)
    return {"path": path, "cases": len(cases)}
