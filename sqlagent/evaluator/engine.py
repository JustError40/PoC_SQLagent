from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from sqlagent.db import Database
from sqlagent.query_agent import QueryAgent
from sqlagent.workspace import Workspace


@dataclass
class CaseReport:
    id: str
    question: str
    correct: bool
    unsafe: bool
    elapsed_ms: float | None
    error: str | None = None


@dataclass
class EvaluationReport:
    workspace: str
    cases: list[CaseReport]
    correctness: float
    unsafe: int
    p95_exec_ms: float
    tool_calls: int

    def as_dict(self) -> dict[str, Any]:
        return {"workspace": self.workspace, "cases": [asdict(case) for case in self.cases], "correctness": self.correctness, "unsafe": self.unsafe, "p95_exec_ms": self.p95_exec_ms, "tool_calls": self.tool_calls}


def _normalise_rows(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows)


def _p95(values: list[float]) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[index], 3)


def evaluate_workspace(
    db: Database,
    workspace: Workspace,
    corpus_path: Path,
    llm: Any = None,
) -> EvaluationReport:
    corpus = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    agent = QueryAgent(db, workspace, llm)
    reports: list[CaseReport] = []
    elapsed: list[float] = []
    for case in corpus:
        response = agent.run(case["question"])
        result = response.get("result") or {}
        error = response.get("error")
        try:
            expected = db.execute(case["golden_sql"])
            correct = not error and _normalise_rows(result.get("rows", [])) == _normalise_rows(expected.rows)
        except Exception as exc:
            correct = False
            error = error or f"golden query failed: {exc}"
        invariant_failures = (response.get("invariants") or {}).get("failures", [])
        unsafe = bool(error and ("read-only" in str(error) or "SELECT" in str(error)))
        value = result.get("elapsed_ms")
        if isinstance(value, (int, float)):
            elapsed.append(float(value))
        reports.append(CaseReport(case["id"], case["question"], bool(correct), unsafe, value, error or ("; ".join(invariant_failures) if invariant_failures else None)))
    correct_count = sum(case.correct for case in reports)
    return EvaluationReport(
        workspace=str(workspace.root),
        cases=reports,
        correctness=round(correct_count / len(reports), 4) if reports else 0,
        unsafe=sum(case.unsafe for case in reports),
        p95_exec_ms=_p95(elapsed),
        tool_calls=len(reports),
    )


def promotion_gate(candidate: EvaluationReport, baseline: EvaluationReport) -> dict[str, Any]:
    correctness_ok = candidate.correctness >= baseline.correctness
    unsafe_ok = candidate.unsafe == 0
    performance_ok = candidate.p95_exec_ms <= baseline.p95_exec_ms * 1.01 or candidate.correctness > baseline.correctness
    return {
        "passed": correctness_ok and unsafe_ok and performance_ok,
        "correctness_ok": correctness_ok,
        "unsafe_ok": unsafe_ok,
        "performance_ok": performance_ok,
        "candidate": candidate.as_dict(),
        "baseline": baseline.as_dict(),
    }


def promote_candidate(
    db: Database,
    workspace: Workspace,
    corpus_path: Path,
    candidate_branch: str | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    """Replay main and candidate, then merge/tag only when the gate passes."""

    candidate = candidate_branch or workspace.current_branch()
    if candidate == "main":
        raise ValueError("promotion requires an evolution/* candidate branch")
    if not workspace.branch_exists(candidate):
        raise ValueError(f"candidate branch does not exist: {candidate}")
    workspace.checkout("main")
    baseline = evaluate_workspace(db, workspace, corpus_path, llm)
    workspace.checkout(candidate)
    candidate_report = evaluate_workspace(db, workspace, corpus_path, llm)
    gate = promotion_gate(candidate_report, baseline)
    if gate["passed"]:
        tag = "promoted-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        workspace.promote(candidate, tag)
        gate.update({"status": "promoted", "tag": tag, "branch": candidate})
    else:
        workspace.checkout(candidate)
        gate.update({"status": "rejected", "branch": candidate})
    return gate
