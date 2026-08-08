from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlagent.db import Database
from sqlagent.query_agent import QueryAgent
from sqlagent.workspace import Workspace

class EvaluatorMutationError(RuntimeError):
    pass


def default_corpus_path(_workspace: Workspace, project_root: Path) -> Path:
    """Campaign corpus is project/run input, never a learned skill artifact."""

    return project_root / "evals" / "regression.jsonl"


@dataclass
class CaseReport:
    id: str
    question: str
    outcome: str
    unsafe: bool
    elapsed_ms: float | None
    sql: str | None = None
    result_hash: str | None = None
    error: dict[str, Any] | None = None
    expected_change: bool = False

    @property
    def correct(self) -> bool:  # legacy compatibility; never reported as accuracy
        return self.outcome == "answered"


@dataclass
class EvaluationReport:
    workspace: str
    commit_sha: str | None
    cases: list[CaseReport]
    answered: int
    clarified: int
    pipeline_failed: int
    unsafe: int
    p95_exec_ms: float
    tool_calls: int
    corpus_checksum: str
    database_checksum: str
    tree_hash: str | None

    @property
    def correctness(self) -> float:  # legacy compatibility; omitted from serialized report
        return self.answered / len(self.cases) if self.cases else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "commit_sha": self.commit_sha,
            "cases": [asdict(case) for case in self.cases],
            "completion": {
                "total": len(self.cases),
                "answered": self.answered,
                "clarified": self.clarified,
                "pipeline_failed": self.pipeline_failed,
            },
            "useful_outcomes": self.answered + self.clarified,
            "unsafe": self.unsafe,
            "p95_exec_ms": self.p95_exec_ms,
            "tool_calls": self.tool_calls,
            "corpus_checksum": self.corpus_checksum,
            "database_checksum": self.database_checksum,
            "tree_hash": self.tree_hash,
        }


def _p95(values: list[float]) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[index], 3)


def _checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _database_checksum(db: Database) -> str:
    try:
        inventory = db.table_inventory()
        payload = json.dumps(inventory, sort_keys=True, default=str).encode()
    except Exception:
        payload = str(getattr(db, "dsn", type(db).__name__)).encode()
    return _checksum_bytes(payload)


def _result_hash(rows: list[dict[str, Any]]) -> str:
    normalized = sorted(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows)
    return _checksum_bytes("\n".join(normalized).encode())


def evaluate_workspace(
    db: Database,
    workspace: Workspace,
    corpus_path: Path,
    llm: Any = None,
    *,
    telemetry_dir: Path | None = None,
) -> EvaluationReport:
    """Sequential, read-only evaluation without a correctness oracle."""

    corpus_bytes = corpus_path.read_bytes()
    corpus = [json.loads(line) for line in corpus_bytes.decode().splitlines() if line.strip()]
    before_state = workspace.filesystem_state()
    before_tree = workspace.tree_hash() if (workspace.root / ".git").exists() else None
    commit_sha = workspace.sha() if (workspace.root / ".git").exists() else None
    agent = QueryAgent(db, workspace, llm, read_only_evaluation=True)
    reports: list[CaseReport] = []
    elapsed: list[float] = []
    traces: list[dict[str, Any]] = []
    for position, case in enumerate(corpus):
        response = agent.run(str(case["question"]))
        outcome = str(response.get("status") or "pipeline_failed")
        if outcome not in {"answered", "clarified", "pipeline_failed"}:
            outcome = "pipeline_failed"
        result = response.get("result") or {}
        value = result.get("elapsed_ms")
        if isinstance(value, (int, float)):
            elapsed.append(float(value))
        error_info = response.get("error_info")
        unsafe = bool(error_info and error_info.get("type") == "sql_validation_failed")
        reports.append(
            CaseReport(
                id=str(case.get("id") or position + 1),
                question=str(case["question"]),
                outcome=outcome,
                unsafe=unsafe,
                elapsed_ms=float(value) if isinstance(value, (int, float)) else None,
                sql=response.get("sql"),
                result_hash=(
                    _result_hash(result.get("rows") or [])
                    if outcome == "answered"
                    else (
                        _checksum_bytes(str(response.get("clarification") or "").encode())
                        if outcome == "clarified"
                        else None
                    )
                ),
                error=error_info,
                expected_change=bool(case.get("expected_change", False)),
            )
        )
        traces.append(response.get("telemetry") or {"request_id": response.get("request_id"), "spans": []})
    after_state = workspace.filesystem_state()
    after_tree = workspace.tree_hash() if (workspace.root / ".git").exists() else None
    if before_state != after_state or before_tree != after_tree:
        raise EvaluatorMutationError("read-only evaluator changed the skill filesystem or Git tree")
    report = EvaluationReport(
        workspace=str(workspace.root),
        commit_sha=commit_sha,
        cases=reports,
        answered=sum(case.outcome == "answered" for case in reports),
        clarified=sum(case.outcome == "clarified" for case in reports),
        pipeline_failed=sum(case.outcome == "pipeline_failed" for case in reports),
        unsafe=sum(case.unsafe for case in reports),
        p95_exec_ms=_p95(elapsed),
        tool_calls=sum(len((trace.get("spans") or [])) for trace in traces),
        corpus_checksum=_checksum_bytes(corpus_bytes),
        database_checksum=_database_checksum(db),
        tree_hash=after_tree,
    )
    if telemetry_dir is not None:
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        (telemetry_dir / "traces.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False, default=str) + "\n" for item in traces),
            encoding="utf-8",
        )
        (telemetry_dir / "run-manifest.json").write_text(
            json.dumps(
                {
                    "commit_sha": commit_sha,
                    "tree_hash": after_tree,
                    "corpus_checksum": report.corpus_checksum,
                    "database_checksum": report.database_checksum,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return report


def promotion_gate(
    candidate: EvaluationReport,
    baseline: EvaluationReport,
    db: Database | None = None,
    target_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    baseline_by_id = {case.id: case for case in baseline.cases}
    candidate_by_id = {case.id: case for case in candidate.cases}
    targets = set(target_case_ids or [case.id for case in candidate.cases if case.expected_change])
    target_rescued = all(
        baseline_by_id.get(case_id) is not None
        and baseline_by_id[case_id].outcome == "pipeline_failed"
        and candidate_by_id.get(case_id) is not None
        and candidate_by_id[case_id].outcome in {"answered", "clarified"}
        for case_id in targets
    )
    regressions = [
        case_id
        for case_id, old in baseline_by_id.items()
        if old.outcome == "answered"
        and (candidate_by_id.get(case_id) is None or candidate_by_id[case_id].outcome == "pipeline_failed")
    ]
    non_equivalent: list[str] = []
    for case_id, old in baseline_by_id.items():
        new = candidate_by_id.get(case_id)
        if case_id in targets or old.outcome != "answered" or new is None or new.outcome != "answered":
            continue
        if db is not None and old.sql and new.sql:
            result = db.compare_queries_full(old.sql, new.sql)
            equivalent = result.equivalent if hasattr(result, "equivalent") else bool(result.get("equivalent"))
        else:
            equivalent = old.result_hash == new.result_hash
        if not equivalent:
            non_equivalent.append(case_id)
    unsafe_ok = candidate.unsafe == 0
    snapshot_ok = (
        candidate.database_checksum == baseline.database_checksum
        and candidate.corpus_checksum == baseline.corpus_checksum
    )
    performance_ok = candidate.p95_exec_ms <= baseline.p95_exec_ms * 1.01
    passed = target_rescued and unsafe_ok and snapshot_ok and not regressions and not non_equivalent and performance_ok
    return {
        "passed": passed,
        "target_rescued": target_rescued,
        "unsafe_ok": unsafe_ok,
        "snapshot_ok": snapshot_ok,
        "regression_cases": regressions,
        "non_equivalent_cases": non_equivalent,
        "performance_ok": performance_ok,
        "candidate": candidate.as_dict(),
        "baseline": baseline.as_dict(),
    }


def _evaluate_refs(
    db: Database,
    workspace: Workspace,
    corpus_path: Path,
    baseline_ref: str,
    candidate_ref: str,
    llm: Any,
    run_dir: Path,
) -> tuple[EvaluationReport, EvaluationReport]:
    token = uuid.uuid4().hex
    root = run_dir / "evaluator-worktrees" / token
    evidence_root = run_dir / "attempts" / token
    baseline_path, candidate_path = root / "baseline", root / "candidate"
    baseline_ws = workspace.create_detached_worktree(baseline_ref, baseline_path)
    candidate_ws = workspace.create_detached_worktree(candidate_ref, candidate_path)
    try:
        baseline = evaluate_workspace(db, baseline_ws, corpus_path, llm, telemetry_dir=evidence_root / "baseline")
        candidate = evaluate_workspace(db, candidate_ws, corpus_path, llm, telemetry_dir=evidence_root / "candidate")
        return baseline, candidate
    finally:
        workspace.remove_worktree(candidate_path)
        workspace.remove_worktree(baseline_path)
        shutil.rmtree(root, ignore_errors=True)


def promote_candidate(
    db: Database,
    workspace: Workspace,
    corpus_path: Path,
    candidate_branch: str | None = None,
    llm: Any = None,
    *,
    run_dir: Path | None = None,
    target_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    candidate = candidate_branch or workspace.current_branch()
    if candidate == "main":
        raise ValueError("promotion requires an evolution/* candidate branch")
    if not workspace.branch_exists(candidate):
        raise ValueError(f"candidate branch does not exist: {candidate}")
    run_dir = (run_dir or workspace.root.parent / "evaluator").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    baseline_sha = workspace.sha("main")
    candidate_sha = workspace.sha(candidate)
    baseline, candidate_report = _evaluate_refs(
        db, workspace, corpus_path, baseline_sha, candidate_sha, llm, run_dir
    )
    gate = promotion_gate(candidate_report, baseline, db, target_case_ids)
    with workspace.promotion_lock():
        current_main = workspace.sha("main")
        if current_main != baseline_sha:
            # Main advanced while evaluation was running. Rebase in an isolated
            # worktree and repeat the entire immutable gate.
            candidate_ws = workspace.worktree_for_branch(candidate)
            temporary_rebase = candidate_ws is None
            rebase_root = run_dir / "rebase-worktree"
            if candidate_ws is None:
                if rebase_root.exists():
                    shutil.rmtree(rebase_root)
                workspace._git("worktree", "add", str(rebase_root), candidate)
                candidate_ws = Workspace(rebase_root)
            try:
                candidate_ws._git("rebase", "main")
            finally:
                if temporary_rebase:
                    workspace.remove_worktree(rebase_root)
            baseline_sha = current_main
            candidate_sha = workspace.sha(candidate)
            baseline, candidate_report = _evaluate_refs(
                db, workspace, corpus_path, baseline_sha, candidate_sha, llm, run_dir / "reevaluation"
            )
            gate = promotion_gate(candidate_report, baseline, db, target_case_ids)
            gate["reevaluated_after_rebase"] = True
        if gate["passed"]:
            tag = "promoted-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            if workspace.current_branch() != "main":
                workspace.checkout("main")
            workspace._git("merge", "--no-ff", candidate, "-m", f"Promote {candidate}")
            workspace._git("tag", tag)
            gate.update({"status": "promoted", "tag": tag, "branch": candidate, "promotion_commit": workspace.sha()})
        else:
            gate.update({"status": "rejected", "branch": candidate})
    return gate
