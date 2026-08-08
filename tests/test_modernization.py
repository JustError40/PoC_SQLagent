from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from sqlagent.analytical import AnalyticalPlanCompiler, AnalyticalPlanError, compile_analytical_plan
from sqlagent.concurrency import AdaptiveLimiter
from sqlagent.db import Database
from sqlagent.errors import ErrorType, classify_error
from sqlagent.evaluator.engine import CaseReport, EvaluationReport, promotion_gate
from sqlagent.failure_queue import FailureQueue
from sqlagent.provenance import ProvenanceRecord, ProvenanceStore
from sqlagent.query_agent.graph import QueryAgent, recursion_limit_for_attempts
from sqlagent.workspace import Workspace
from sqlagent.scratch import ScratchExecutor
from scripts.campaign_preflight import required_tmpfs_bytes
from scripts.test_campaign import run_questions_ordered
from sqlagent import web


def test_error_taxonomy_is_complete_and_structured() -> None:
    assert {item.value for item in ErrorType} == {
        "llm_timeout", "llm_transport_error", "llm_invalid_json", "llm_schema_violation",
        "schema_selection_failed", "plan_assembly_failed", "sql_validation_failed",
        "explain_timeout", "execution_timeout", "db_error", "critic_rejected",
        "react_exhausted", "langgraph_recursion", "serialization_failed",
        "workspace_error", "internal_error",
    }
    error = classify_error("statement timeout", stage="execution")
    assert error.type == ErrorType.EXECUTION_TIMEOUT
    assert error.retryable is True
    assert error.as_dict()["sqlstate"] is None


@pytest.mark.parametrize(
    "message,stage,expected",
    [
        ("invalid JSON", "llm_generation", ErrorType.LLM_INVALID_JSON),
        ("LLM schema violation", "llm_generation", ErrorType.LLM_SCHEMA_VIOLATION),
        ("schema selection failed", "router", ErrorType.SCHEMA_SELECTION_FAILED),
        ("query plan assembly failed", "plan", ErrorType.PLAN_ASSEMBLY_FAILED),
        ("lint failed", "validation", ErrorType.SQL_VALIDATION_FAILED),
        ("timeout", "explain", ErrorType.EXPLAIN_TIMEOUT),
        ("critic rejected", "critic", ErrorType.CRITIC_REJECTED),
        ("repair budget exhausted", "react", ErrorType.REACT_EXHAUSTED),
        ("GraphRecursionError", "langgraph", ErrorType.LANGGRAPH_RECURSION),
        ("serialization failed", "serialization", ErrorType.SERIALIZATION_FAILED),
        ("workspace missing", "workspace", ErrorType.WORKSPACE_ERROR),
    ],
)
def test_error_taxonomy_routes_artificial_failures(message: str, stage: str, expected: ErrorType) -> None:
    assert classify_error(message, stage=stage).type == expected


def test_recursion_budget_scales_with_full_repair_cycle() -> None:
    assert recursion_limit_for_attempts(15) > recursion_limit_for_attempts(2)
    assert recursion_limit_for_attempts(3) - recursion_limit_for_attempts(2) == 6


def test_adaptive_limiter_aimd_reduces_and_recovers() -> None:
    limiter = AdaptiveLimiter(initial=4, stable_window=2)
    limiter.record_pressure()
    assert limiter.limit == 2
    limiter.record_success()
    limiter.record_success()
    assert limiter.limit == 3
    limiter.record_pressure()
    limiter.record_pressure()
    assert limiter.limit == 1


def test_analytical_dag_compiles_union_window_ratio_and_validates_fanout() -> None:
    schema = {"sales": ["month", "customer_id", "revenue"], "returns": ["month", "customer_id", "revenue"]}
    plan = {
        "stages": [
            {"id": "sales_scan", "type": "scan", "table": "sales", "grain": ["customer_id", "month"]},
            {"id": "returns_scan", "type": "scan", "table": "returns", "grain": ["customer_id", "month"]},
            {"id": "channels", "type": "union_all", "inputs": ["sales_scan", "returns_scan"]},
            {
                "id": "monthly", "type": "aggregate", "input": "channels", "group_by": ["month"],
                "measures": [{"agg": "sum", "column": "revenue", "alias": "revenue"}],
            },
            {
                "id": "running", "type": "window", "input": "monthly",
                "expressions": [{"function": "sum", "value": "revenue", "order_by": ["month"], "alias": "cumulative"}],
            },
            {
                "id": "final", "type": "project", "input": "running",
                "expressions": [{"alias": "share", "expr": {"binary": {"left": "revenue", "op": "/", "right": "cumulative"}}}],
            },
        ]
    }
    compiled = compile_analytical_plan(plan, schema)
    assert "UNION ALL" in compiled.sql
    assert "SUM(\"revenue\") OVER (ORDER BY \"month\")" in compiled.sql
    assert "NULLIF(\"cumulative\", 0)" in compiled.sql

    bad = {
        "stages": [
            {"id": "a", "type": "scan", "table": "sales"},
            {"id": "b", "type": "scan", "table": "returns"},
            {"id": "j", "type": "join", "left": "a", "right": "b", "left_key": "customer_id", "right_key": "customer_id", "cardinality": "one_to_many"},
        ]
    }
    with pytest.raises(AnalyticalPlanError, match="allow_fanout"):
        compile_analytical_plan(bad, schema)


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=()):
        self.connection.sql.append(str(sql))

    def fetchone(self):
        return ([{"Plan": {"Total Cost": 9.5, "Plan Rows": 7}}],)


class _Connection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return _Cursor(self)

    def execute(self, sql, params=()):
        self.sql.append(str(sql))
        if "full_difference" in str(sql):
            return type("Result", (), {"fetchone": lambda self: (True,)})()
        return type("Result", (), {"fetchone": lambda self: (None,)})()


class _FakeDatabase(Database):
    def __init__(self) -> None:
        super().__init__("postgresql://example/db", limiter=None)
        self.connection = _Connection()

    def _connection(self):
        return self.connection


def test_db_estimate_never_uses_analyze_and_full_comparison_uses_except_all() -> None:
    db = _FakeDatabase()
    estimate = db.explain_estimate("SELECT 1")
    assert estimate["rows"] == 7
    assert estimate["actual_ms"] is None
    assert "ANALYZE" not in db.connection.sql[-1]
    assert db.compare_queries_full("SELECT 1", "SELECT 1").equivalent is True
    comparison = db.connection.sql[-1]
    assert comparison.count("EXCEPT ALL") == 2
    assert "LIMIT 500" not in comparison


def test_failure_queue_deduplicates_skill_failures_and_separates_incidents(tmp_path: Path) -> None:
    queue = FailureQueue(tmp_path / "failures.sqlite3")
    first = queue.enqueue(request_id="r1", error_type="plan_assembly_failed", stage="plan", message="bad plan")
    second = queue.enqueue(request_id="r2", error_type="plan_assembly_failed", stage="plan", message="bad   plan")
    assert first == second
    assert queue.get(first)["occurrence_count"] == 2
    incident = queue.enqueue(request_id="r3", error_type="db_error", stage="db", message="connection reset")
    assert queue.get(incident)["status"] == "incident"
    claimed = queue.claim()
    assert claimed is not None and claimed.id == first


def test_provenance_is_complete_and_immutable(tmp_path: Path) -> None:
    artifact = tmp_path / "metric.yaml"
    artifact.write_text("metric: revenue\n", encoding="utf-8")
    record = ProvenanceRecord.build(
        artifact_path=artifact, run_id="run", request_id="request", trajectory_id="trajectory",
        base_sha="base", candidate_sha="candidate", attribution="metrics", source_error={"type": "x"},
        evidence_sql_hashes=["sql"], evidence_result_hashes=["result"], provider="litellm", model="model",
        llm_call_ids=["call"], prompt_hashes=["prompt"], schema_hashes=["schema"], db_snapshot="db",
        evaluator_report="report.json", promotion_commit="promotion",
    )
    store = ProvenanceStore(tmp_path / "provenance")
    target = store.write_immutable(record)
    assert json.loads(target.read_text())["artifact_hash"] == record.artifact_hash
    with pytest.raises(FileExistsError):
        store.write_immutable(record)


def test_read_only_query_agent_does_not_write_trajectory(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_text("SKILL.md", "skill\n")
    workspace.write_yaml("manifest.yaml", {"templates": {}})
    before = workspace.filesystem_state()
    result = QueryAgent(object(), workspace, None, read_only_evaluation=True).run("как дела с показателями?")
    assert result["status"] == "clarified"
    assert workspace.filesystem_state() == before
    assert not (workspace.root / "experience" / "trajectories.jsonl").exists()


def _report(cases: list[CaseReport], p95: float = 10.0) -> EvaluationReport:
    return EvaluationReport(
        workspace="skill", commit_sha="sha", cases=cases,
        answered=sum(item.outcome == "answered" for item in cases),
        clarified=sum(item.outcome == "clarified" for item in cases),
        pipeline_failed=sum(item.outcome == "pipeline_failed" for item in cases),
        unsafe=sum(item.unsafe for item in cases), p95_exec_ms=p95, tool_calls=1,
        corpus_checksum="corpus", database_checksum="db", tree_hash="tree",
    )


def test_promotion_gate_uses_rescue_regression_and_equivalence_not_accuracy() -> None:
    baseline = _report([
        CaseReport("target", "q1", "pipeline_failed", False, None, expected_change=True),
        CaseReport("stable", "q2", "answered", False, 1, result_hash="same"),
    ])
    candidate = _report([
        CaseReport("target", "q1", "clarified", False, None, expected_change=True),
        CaseReport("stable", "q2", "answered", False, 1, result_hash="same"),
    ])
    gate = promotion_gate(candidate, baseline)
    assert gate["passed"] is True
    assert "correctness" not in gate["candidate"]


def test_candidate_worktree_never_switches_main_checkout(tmp_path: Path) -> None:
    main = Workspace(tmp_path / "skill")
    main.write_text("SKILL.md", "main\n")
    main.commit("main")
    branch, candidate = main.create_candidate_worktree("request", "metrics", tmp_path / "worktrees")
    try:
        assert branch == "evolution/request-metrics"
        assert main.current_branch() == "main"
        candidate.write_text("metrics/revenue.yaml", "metric: revenue\n")
        candidate.commit("candidate")
        assert main.latest_candidate_branch() == branch
        assert not (main.root / "metrics" / "revenue.yaml").exists()
        assert main.current_branch() == "main"
    finally:
        main.remove_worktree(candidate.root)


def test_campaign_questions_are_concurrent_but_report_order_is_stable() -> None:
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_ask(question: str) -> dict:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02 if question == "first" else 0.005)
        with lock:
            active -= 1
        return {"question": question}

    results = run_questions_ordered(["first", "second", "third"], fake_ask, concurrency=3)
    assert [item["question"] for item in results] == ["first", "second", "third"]
    assert peak > 1


def test_tmpfs_preflight_adds_overhead_and_scratch_names_are_session_isolated() -> None:
    assert required_tmpfs_bytes(1024**3) > 2 * 1024**3
    assert ScratchExecutor._name("request-a", 1) != ScratchExecutor._name("request-b", 1)


def test_materialized_dag_compiles_to_controlled_temp_placeholders() -> None:
    plan = {
        "stages": [
            {"id": "scan", "type": "scan", "table": "sales", "materialize": True},
            {
                "id": "filtered", "type": "filter", "input": "scan",
                "where": {"binary": {"left": "amount", "op": ">", "right": {"literal": 0}}},
            },
        ]
    }
    scratch = AnalyticalPlanCompiler({"sales": ["id", "amount"]}).compile_scratch(plan)
    assert len(scratch.stages) == 1
    assert '{{stage_1}}' in scratch.final_sql
    assert "CREATE" not in " ".join(scratch.stages) + scratch.final_sql


def test_compose_uses_tmpfs_without_postgres_disk_volume() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "/var/lib/postgresql/data:size=${POSTGRES_TMPFS_SIZE_BYTES" in compose
    assert "postgres_data:" not in compose
    assert "./runs:/app/runs" in compose


def test_ask_api_returns_structured_error_and_learning_job(tmp_path: Path, monkeypatch) -> None:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_yaml("manifest.yaml", {"templates": {}})
    queue = FailureQueue(tmp_path / "telemetry" / "failures.sqlite3")

    class Learner:
        def __init__(self) -> None:
            self.started = False

        def start(self) -> bool:
            self.started = True
            return True

    learner = Learner()
    monkeypatch.setattr(web, "runtime", lambda: (object(), workspace, None))
    monkeypatch.setattr(web, "failure_queue", queue)
    monkeypatch.setattr(web, "learner", learner)
    monkeypatch.setattr(
        web,
        "ask",
        lambda *args, **kwargs: {
            "request_id": "request",
            "status": "pipeline_failed",
            "telemetry": {"request_id": "request", "spans": []},
            "error": "execution failed: timeout",
            "error_info": classify_error("timeout", stage="execution").as_dict(),
        },
    )

    result = web.ask_endpoint(web.AskRequest(question="valid question"))

    assert result["request_id"] == "request"
    assert result["error"]["type"] == "execution_timeout"
    assert result["error"]["learning_job_id"]
    assert learner.started is True
