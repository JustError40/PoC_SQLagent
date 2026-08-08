from __future__ import annotations

import re
import json
import math
import contextvars
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable


STAGE_TYPES = {"scan", "filter", "join", "aggregate", "union_all", "window", "rank", "project"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BINARY_OPS = {"+", "-", "*", "/", "=", "!=", "<>", "<", "<=", ">", ">=", "and", "or"}
_AGGREGATES = {"sum", "count", "count_distinct", "avg", "min", "max"}
_WINDOWS = {"row_number", "rank", "dense_rank", "lag", "lead", "sum", "avg", "count"}


class AnalyticalPlanError(ValueError):
    pass


def _ident(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise AnalyticalPlanError(f"unsafe identifier: {value!r}")
    return f'"{value}"'


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def compile_expression(expr: Any, available: set[str]) -> str:
    """Compile the intentionally small expression AST used by analytical plans."""

    if isinstance(expr, str):
        if expr not in available:
            raise AnalyticalPlanError(f"unknown column {expr!r}")
        return _ident(expr)
    if not isinstance(expr, dict) or len(expr) != 1:
        raise AnalyticalPlanError("expression must be a column name or a one-key expression object")
    kind, value = next(iter(expr.items()))
    if kind == "literal":
        return _literal(value)
    if kind == "column":
        return compile_expression(str(value), available)
    if kind == "binary":
        if not isinstance(value, dict) or str(value.get("op", "")).lower() not in _BINARY_OPS:
            raise AnalyticalPlanError("unsupported binary expression")
        op = str(value["op"]).upper()
        left = compile_expression(value.get("left"), available)
        right = compile_expression(value.get("right"), available)
        if op == "/":
            right = f"NULLIF({right}, 0)"
        return f"({left} {op} {right})"
    if kind == "case":
        if not isinstance(value, dict):
            raise AnalyticalPlanError("CASE must be an object")
        clauses = []
        for item in value.get("when", []):
            clauses.append(
                "WHEN "
                + compile_expression(item.get("if"), available)
                + " THEN "
                + compile_expression(item.get("then"), available)
            )
        if not clauses:
            raise AnalyticalPlanError("CASE requires at least one WHEN")
        otherwise = compile_expression(value.get("else", {"literal": None}), available)
        return "CASE " + " ".join(clauses) + f" ELSE {otherwise} END"
    if kind == "date_trunc":
        if not isinstance(value, dict) or value.get("unit") not in {"day", "week", "month", "quarter", "year"}:
            raise AnalyticalPlanError("unsupported date_trunc unit")
        return f"DATE_TRUNC({_literal(value['unit'])}, {compile_expression(value.get('value'), available)})"
    raise AnalyticalPlanError(f"unsupported expression kind {kind!r}")


@dataclass(frozen=True)
class CompiledPlan:
    sql: str
    output_columns: tuple[str, ...]
    grain: tuple[str, ...]
    stages: tuple[str, ...]


@dataclass(frozen=True)
class ScratchCompiledPlan:
    stages: tuple[str, ...]
    final_sql: str


class AnalyticalPlanCompiler:
    def __init__(
        self,
        schema: dict[str, Iterable[str]],
        join_cardinality: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.schema = {table: set(columns) for table, columns in schema.items()}
        self.join_cardinality = join_cardinality or {}

    def compile(self, plan: dict[str, Any]) -> CompiledPlan:
        raw_stages = plan.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise AnalyticalPlanError("analytical plan requires stages")
        ctes: list[str] = []
        outputs: dict[str, set[str]] = {}
        grains: dict[str, tuple[str, ...]] = {}
        for index, stage in enumerate(raw_stages):
            if not isinstance(stage, dict):
                raise AnalyticalPlanError("each stage must be an object")
            stage_id = str(stage.get("id") or f"stage_{index + 1}")
            kind = str(stage.get("type") or "")
            _ident(stage_id)
            if kind not in STAGE_TYPES:
                raise AnalyticalPlanError(f"unsupported stage type {kind!r}")
            sql, columns, grain = self._compile_stage(kind, stage, outputs, grains)
            ctes.append(f"{_ident(stage_id)} AS ({sql})")
            outputs[stage_id] = columns
            grains[stage_id] = grain
        final_id = str(plan.get("output") or raw_stages[-1].get("id") or f"stage_{len(raw_stages)}")
        if final_id not in outputs:
            raise AnalyticalPlanError(f"unknown output stage {final_id!r}")
        return CompiledPlan(
            sql="WITH " + ",\n".join(ctes) + f"\nSELECT * FROM {_ident(final_id)}",
            output_columns=tuple(sorted(outputs[final_id])),
            grain=grains[final_id],
            stages=tuple(outputs),
        )

    def compile_scratch(self, plan: dict[str, Any]) -> ScratchCompiledPlan:
        """Compile a DAG into sequential SQL using {{stage_N}} temp placeholders."""

        raw_stages = plan.get("stages")
        if not isinstance(raw_stages, list) or len(raw_stages) < 2:
            raise AnalyticalPlanError("scratch plan requires at least two stages")
        outputs: dict[str, set[str]] = {}
        grains: dict[str, tuple[str, ...]] = {}
        stage_ids: list[str] = []
        queries: list[str] = []
        for index, stage in enumerate(raw_stages):
            stage_id = str(stage.get("id") or f"stage_{index + 1}")
            kind = str(stage.get("type") or "")
            _ident(stage_id)
            if kind not in STAGE_TYPES:
                raise AnalyticalPlanError(f"unsupported stage type {kind!r}")
            sql, columns, grain = self._compile_stage(kind, stage, outputs, grains)
            for previous, previous_id in enumerate(stage_ids, 1):
                sql = sql.replace(_ident(previous_id), f"{{{{stage_{previous}}}}}")
            stage_ids.append(stage_id)
            queries.append(sql)
            outputs[stage_id] = columns
            grains[stage_id] = grain
        final_id = str(plan.get("output") or stage_ids[-1])
        if final_id not in stage_ids:
            raise AnalyticalPlanError(f"unknown output stage {final_id!r}")
        final_index = stage_ids.index(final_id)
        if final_index == 0:
            raise AnalyticalPlanError("scratch output cannot be the first stage")
        return ScratchCompiledPlan(tuple(queries[:final_index]), queries[final_index])

    def _input(self, stage: dict[str, Any], outputs: dict[str, set[str]]) -> tuple[str, set[str]]:
        source = str(stage.get("input") or "")
        if source not in outputs:
            raise AnalyticalPlanError(f"unknown or forward input stage {source!r}")
        return source, outputs[source]

    def _compile_stage(
        self,
        kind: str,
        stage: dict[str, Any],
        outputs: dict[str, set[str]],
        grains: dict[str, tuple[str, ...]],
    ) -> tuple[str, set[str], tuple[str, ...]]:
        if kind == "scan":
            table = str(stage.get("table") or "")
            if table not in self.schema:
                raise AnalyticalPlanError(f"unknown table {table!r}")
            selected = [str(item) for item in stage.get("columns") or sorted(self.schema[table])]
            unknown = set(selected) - self.schema[table]
            if unknown:
                raise AnalyticalPlanError(f"unknown columns in {table}: {sorted(unknown)}")
            grain = tuple(str(item) for item in stage.get("grain") or ())
            if not set(grain) <= set(selected):
                raise AnalyticalPlanError("scan grain must be present in selected columns")
            return f"SELECT {', '.join(_ident(item) for item in selected)} FROM {_ident(table)}", set(selected), grain

        if kind == "filter":
            source, columns = self._input(stage, outputs)
            predicate = compile_expression(stage.get("where"), columns)
            return f"SELECT * FROM {_ident(source)} WHERE {predicate}", set(columns), grains[source]

        if kind == "join":
            left = str(stage.get("left") or "")
            right = str(stage.get("right") or "")
            if left not in outputs or right not in outputs:
                raise AnalyticalPlanError("join inputs must reference prior stages")
            left_key, right_key = str(stage.get("left_key") or ""), str(stage.get("right_key") or "")
            if left_key not in outputs[left] or right_key not in outputs[right]:
                raise AnalyticalPlanError("join key is not present in its input")
            cardinality = str(stage.get("cardinality") or self.join_cardinality.get((left, right), ""))
            if cardinality not in {"one_to_one", "many_to_one", "one_to_many"}:
                raise AnalyticalPlanError("join cardinality must be declared")
            if cardinality == "one_to_many" and not stage.get("allow_fanout"):
                raise AnalyticalPlanError("one_to_many join requires explicit allow_fanout")
            overlap = outputs[left] & outputs[right]
            if overlap:
                raise AnalyticalPlanError(f"join has ambiguous output columns: {sorted(overlap)}")
            how = str(stage.get("how") or "inner").lower()
            if how not in {"inner", "left"}:
                raise AnalyticalPlanError("only inner and left joins are supported")
            sql = (
                f"SELECT l.*, r.* FROM {_ident(left)} AS l {how.upper()} JOIN {_ident(right)} AS r "
                f"ON l.{_ident(left_key)} = r.{_ident(right_key)}"
            )
            grain = grains[left] if cardinality in {"one_to_one", "many_to_one"} else tuple()
            return sql, outputs[left] | outputs[right], grain

        if kind == "aggregate":
            source, columns = self._input(stage, outputs)
            group_by = [str(item) for item in stage.get("group_by") or []]
            if not set(group_by) <= columns:
                raise AnalyticalPlanError("aggregate group_by contains an unknown column")
            select = [_ident(item) for item in group_by]
            output = set(group_by)
            for measure in stage.get("measures") or []:
                agg = str(measure.get("agg") or "").lower()
                alias = str(measure.get("alias") or "")
                column = str(measure.get("column") or "*")
                if agg not in _AGGREGATES or not alias:
                    raise AnalyticalPlanError("unsupported aggregate or missing alias")
                if column != "*" and column not in columns:
                    raise AnalyticalPlanError(f"unknown aggregate column {column!r}")
                argument = "*" if column == "*" else _ident(column)
                expression = f"COUNT(DISTINCT {argument})" if agg == "count_distinct" else f"{agg.upper()}({argument})"
                select.append(f"{expression} AS {_ident(alias)}")
                output.add(alias)
            if not select:
                raise AnalyticalPlanError("aggregate selects nothing")
            group_sql = " GROUP BY " + ", ".join(_ident(item) for item in group_by) if group_by else ""
            return f"SELECT {', '.join(select)} FROM {_ident(source)}{group_sql}", output, tuple(group_by)

        if kind == "union_all":
            inputs = [str(item) for item in stage.get("inputs") or []]
            if len(inputs) < 2 or any(item not in outputs for item in inputs):
                raise AnalyticalPlanError("union_all requires at least two prior inputs")
            first = outputs[inputs[0]]
            if any(outputs[item] != first for item in inputs[1:]):
                raise AnalyticalPlanError("union_all inputs must expose identical columns")
            ordered = sorted(first)
            sql = " UNION ALL ".join(
                f"SELECT {', '.join(_ident(column) for column in ordered)} FROM {_ident(item)}" for item in inputs
            )
            grain = grains[inputs[0]] if all(grains[item] == grains[inputs[0]] for item in inputs) else tuple()
            return sql, set(first), grain

        source, columns = self._input(stage, outputs)
        expressions = stage.get("expressions") or []
        select = ["*"] if stage.get("keep", True) else []
        output = set(columns) if stage.get("keep", True) else set()
        for item in expressions:
            alias = str(item.get("alias") or "")
            if not alias:
                raise AnalyticalPlanError("derived expression requires alias")
            if kind in {"window", "rank"}:
                function = str(item.get("function") or ("rank" if kind == "rank" else "")).lower()
                if function not in _WINDOWS:
                    raise AnalyticalPlanError(f"unsupported window function {function!r}")
                argument = "" if function in {"row_number", "rank", "dense_rank"} else compile_expression(item.get("value"), columns)
                partition = [str(value) for value in item.get("partition_by") or []]
                order = [str(value) for value in item.get("order_by") or []]
                if not set(partition + order) <= columns:
                    raise AnalyticalPlanError("window references an unknown column")
                over = []
                if partition:
                    over.append("PARTITION BY " + ", ".join(_ident(value) for value in partition))
                if order:
                    over.append("ORDER BY " + ", ".join(_ident(value) for value in order))
                compiled = f"{function.upper()}({argument}) OVER ({' '.join(over)})"
            else:
                compiled = compile_expression(item.get("expr"), columns)
            select.append(f"{compiled} AS {_ident(alias)}")
            output.add(alias)
        if not select:
            raise AnalyticalPlanError("project selects nothing")
        return f"SELECT {', '.join(select)} FROM {_ident(source)}", output, grains[source]


def compile_analytical_plan(
    plan: dict[str, Any],
    schema: dict[str, Iterable[str]],
    join_cardinality: dict[tuple[str, str], str] | None = None,
) -> CompiledPlan:
    return AnalyticalPlanCompiler(schema, join_cardinality).compile(plan)


_COMPLEX_TERMS = (
    "cohort", "retention", "pareto", "cumulative", "running total", "rank", "window",
    "union", "period over period", "year over year", "month over month",
    "когорт", "удержан", "парето", "накоп", "ранж", "сравн", "период",
)


def is_complex_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in _COMPLEX_TERMS)


def select_analytical_candidate(
    *,
    question: str,
    context: dict[str, Any],
    schema: dict[str, Iterable[str]],
    llm: Any,
    db: Any,
) -> tuple[dict[str, Any], CompiledPlan, dict[str, Any]]:
    """Build two independent decompositions, then EXPLAIN valid SQL in parallel."""

    prompts = (
        "Decompose the metric and business semantics, then return a complete analytical-plan DAG. "
        "Use only scan/filter/join/aggregate/union_all/window/rank/project and declare grain/cardinality.",
        "Plan tables and relationships for this question, then return a complete analytical-plan DAG. "
        "Use only supplied tables/columns; reject fanout unless explicitly preaggregated.",
    )

    def propose(prompt: str) -> dict[str, Any]:
        return llm.chat_json(
            prompt,
            json.dumps({"question": question, **context}, ensure_ascii=False, default=str),
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="analytical-decompose") as pool:
        futures = [pool.submit(contextvars.copy_context().run, propose, prompt) for prompt in prompts]
        proposals = [future.result() for future in futures]
    compiled: list[tuple[dict[str, Any], CompiledPlan]] = []
    for proposal in proposals:
        if isinstance(proposal, dict) and proposal.get("stages"):
            try:
                compiled.append((proposal, compile_analytical_plan(proposal, schema)))
            except AnalyticalPlanError:
                continue
    if not compiled:
        raise AnalyticalPlanError("no valid analytical DAG candidate")

    def estimate(item: tuple[dict[str, Any], CompiledPlan]) -> tuple[dict[str, Any], CompiledPlan, dict[str, Any]]:
        method = getattr(db, "explain_estimate", None) or db.explain
        return item[0], item[1], method(item[1].sql)

    checked: list[tuple[dict[str, Any], CompiledPlan, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(compiled)), thread_name_prefix="analytical-explain") as pool:
        futures = [pool.submit(contextvars.copy_context().run, estimate, item) for item in compiled]
        for future in as_completed(futures):
            try:
                checked.append(future.result())
            except Exception:
                continue
    if not checked:
        raise AnalyticalPlanError("all analytical DAG candidates failed EXPLAIN")
    return min(checked, key=lambda item: float(item[2].get("total_cost") or math.inf))
