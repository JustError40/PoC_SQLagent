from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from sqlagent.config import Settings
from sqlagent.db import Database
from sqlagent.evaluator import default_corpus_path, evaluate_workspace, promote_candidate
from sqlagent.evolution import run_evolution
from sqlagent.explorer import run_exploration
from sqlagent.llm import LLMUnavailable, OllamaClient, OpenCodeGoClient, build_llm
from sqlagent.query_agent import ask
from sqlagent.surveyor import run_survey
from sqlagent.trajectories import read_trajectories
from sqlagent.verification import verify_skill
from sqlagent.workspace import Workspace


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "web_static"
settings = Settings.from_env()

_service_lock = threading.Lock()
_services: dict[str, dict[str, str]] = {
    "postgres": {"status": "configured", "detail": "waiting for an agent database response"},
    "ollama": {"status": "configured", "detail": f"{settings.llm_provider}/{settings.active_llm_model}; waiting for an agent response"},
}


def _set_service(name: str, status: str, detail: str) -> None:
    with _service_lock:
        _services[name] = {"status": status, "detail": detail}


def _database_event(event: str, detail: str) -> None:
    _set_service("postgres", "error" if event == "error" else "ready", detail)


def _ollama_event(event: str, detail: str) -> None:
    status = {
        "request_started": "running",
        "response": "ready",
        "response_cached": "ready",
        "cache_invalid": "running",
        "error": "error",
    }.get(event, "configured")
    _set_service("ollama", status, detail)


def _service_snapshot() -> dict[str, dict[str, str]]:
    with _service_lock:
        return {name: dict(value) for name, value in _services.items()}


def runtime() -> tuple[Database, Workspace, OllamaClient]:
    workspace = Workspace(settings.workspace_path)
    return (
        Database(settings.database_url, settings.max_result_rows, settings.statement_timeout_ms, _database_event),
        workspace,
        build_llm(
            provider=settings.llm_provider,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            opencode_go_base_url=settings.opencode_go_base_url,
            opencode_go_api_key=settings.opencode_go_api_key,
            opencode_go_model=settings.opencode_go_model,
            litellm_base_url=settings.litellm_base_url,
            litellm_api_key=settings.litellm_api_key,
            litellm_model=settings.litellm_model,
            cache_dir=workspace.root / ".cache" / "llm",
            event_hook=_ollama_event,
        ),
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, name: str, operation: Callable[[], Any]) -> str:
        job_id = uuid.uuid4().hex[:10]
        with self._lock:
            if any(job["name"] == name and job["status"] == "running" for job in self._jobs.values()):
                raise RuntimeError(f"{name} is already running")
            self._jobs[job_id] = {
                "id": job_id,
                "name": name,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

        def worker() -> None:
            try:
                result = operation()
                with self._lock:
                    self._jobs[job_id].update({"status": "completed", "result": result})
            except Exception as exc:  # surfaced in the UI as a job failure
                with self._lock:
                    self._jobs[job_id].update({"status": "failed", "error": str(exc)})
            finally:
                with self._lock:
                    self._jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()

        threading.Thread(target=worker, name=f"sqlagent-{name}-{job_id}", daemon=True).start()
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._jobs.get(job_id, {})) or None

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed([dict(job) for job in self._jobs.values()]))[:12]


jobs = JobStore()
app = FastAPI(title="SQL Agent Field Console", docs_url="/api/docs", redoc_url=None)

SIGNAL_STAGES = ("ingest", "reason", "learn", "promote")
_signal_lock = threading.Lock()
_signal: dict[str, dict[str, str]] = {
    "ingest": {"status": "pending", "detail": "connecting to PostgreSQL"},
    "reason": {"status": "pending", "detail": "waiting for model and survey"},
    "learn": {"status": "pending", "detail": "waiting for trajectories"},
    "promote": {"status": "pending", "detail": "waiting for evaluator"},
}
_active_queries = 0


def _set_signal(stage: str, status: str, detail: str) -> None:
    with _signal_lock:
        _signal[stage] = {"status": status, "detail": detail}


def _signal_snapshot(
    db_status: str,
    llm_status: str,
    workspace: Workspace,
    trajectories: list[dict[str, Any]],
) -> dict[str, Any]:
    with _signal_lock:
        snapshot = {stage: dict(_signal[stage]) for stage in SIGNAL_STAGES}
        query_running = _active_queries > 0

    db_ok = db_status in {"configured", "ready", "running"}
    db_responded = db_status in {"ready", "running"}
    llm_ok = llm_status in {"configured", "ready", "running"}
    defaults = {
        "ingest": {
            "status": "ready" if db_responded else ("offline" if db_status == "error" else "pending"),
            "detail": "PostgreSQL responded" if db_responded else ("database unavailable" if db_status == "error" else "awaiting first database response"),
        },
        "reason": {
            "status": "ready" if db_ok and llm_ok and (workspace.root / "manifest.yaml").exists() else "pending",
            "detail": "Query Agent ready" if db_ok and llm_ok and (workspace.root / "manifest.yaml").exists() else "waiting for model or survey",
        },
        "learn": {
            "status": "ready" if trajectories else "pending",
            "detail": f"{len(trajectories)} trajectories observed" if trajectories else "waiting for trajectories",
        },
        "promote": {"status": "pending", "detail": "waiting for evaluator"},
    }
    for stage in SIGNAL_STAGES:
        if snapshot[stage]["status"] in {"pending", "ready"}:
            snapshot[stage] = defaults[stage]
    if query_running:
        snapshot["reason"] = {"status": "running", "detail": "routing, EXPLAIN and execution"}
    return snapshot


def _tracked_operation(stage: str, operation: Callable[[], Any], success_status: str = "ready") -> Callable[[], Any]:
    def run() -> Any:
        _set_signal(stage, "running", "agent is processing")
        try:
            result = operation()
            detail = "completed"
            if isinstance(result, dict):
                detail = str(result.get("branch") or result.get("status") or "completed")
            _set_signal(stage, success_status, detail)
            if stage == "ingest":
                _set_service("postgres", "ready", "Surveyor received database metadata")
            if stage == "learn" and isinstance(result, dict) and result.get("branch"):
                _set_signal("promote", "candidate", str(result["branch"]))
            return result
        except Exception as exc:
            _set_signal(stage, "error", str(exc)[:160])
            raise

    return run


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/assets/{filename}", include_in_schema=False)
def asset(filename: str) -> FileResponse:
    path = STATIC / filename
    if not path.exists() or path.parent != STATIC:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)


@app.get("/api/health")
def health() -> dict[str, Any]:
    workspace = Workspace(settings.workspace_path)
    services = _service_snapshot()
    workspace_ok = (workspace.root / "manifest.yaml").exists()
    return {
        "ok": all(service["status"] != "error" for service in services.values()) and workspace_ok,
        "postgres": services["postgres"],
        "ollama": {
            **services["ollama"],
            "provider": settings.llm_provider,
            "model": settings.active_llm_model,
            "base_url": settings.active_llm_base_url,
        },
        "workspace": {"ok": workspace_ok, "path": str(workspace.root)},
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    workspace = Workspace(settings.workspace_path)
    dataset = settings.database_url.rstrip("/").rsplit("/", 1)[-1]
    services = _service_snapshot()
    trajectories = read_trajectories(workspace.root / "experience" / "trajectories.jsonl")
    latest = []
    for item in trajectories[-8:][::-1]:
        telemetry = item.get("telemetry") or {}
        latest.append({
            "question": item.get("question"),
            "status": "clarification" if telemetry.get("clarification_requested") else ("ok" if (item.get("invariants") or {}).get("passed") else "failed"),
            "elapsed_ms": (item.get("result") or {}).get("elapsed_ms"),
            "created_at": item.get("created_at"),
            "telemetry": telemetry,
            "react_attempts": (item.get("react") or {}).get("attempts", 0),
        })
    branch = None
    if workspace.root.exists() and (workspace.root / ".git").exists():
        try:
            branch = workspace.current_branch()
        except Exception:
            branch = None
    manifest = workspace.read_yaml("manifest.yaml", default={}) or {}
    if not isinstance(manifest, dict):  # corrupt or legacy list-shaped manifest
        manifest = {}
    templates = manifest.get("templates") or {}
    exploration = read_trajectories(workspace.root / "experience" / "exploration.jsonl")
    signal = _signal_snapshot(services["postgres"]["status"], services["ollama"]["status"], workspace, trajectories)
    active_signal = any(item["status"] == "running" for item in signal.values())
    signal_state = "processing" if active_signal else "ready"
    if any(item["status"] == "error" for item in signal.values()):
        signal_state = "attention"
    elif signal["promote"]["status"] in {"candidate", "evaluated"}:
        signal_state = "candidate"
    elif signal["promote"]["status"] == "promoted":
        signal_state = "promoted"
    return {
        "dataset": dataset,
        "postgres": services["postgres"],
        "ollama": {
            **services["ollama"],
            "provider": settings.llm_provider,
            "model": settings.active_llm_model,
        },
        "workspace": {"status": "ready" if (workspace.root / "manifest.yaml").exists() else "needs_survey", "branch": branch, "path": str(workspace.root), "templates_count": len(templates)},
        "pipeline": {
            "surveyor": "ready" if (workspace.root / "raw" / "schema_snapshot.json").exists() else "pending",
            "explorer": "ready" if templates or exploration else "pending",
            "query_agent": "ready" if (workspace.root / "manifest.yaml").exists() else "pending",
            "evolution": "ready" if trajectories else "waiting_for_trajectories",
            "evaluator": "ready" if trajectories else "waiting_for_trajectories",
        },
        "trajectory_count": len(trajectories),
        "exploration_count": len(exploration),
        "latest_trajectories": latest,
        "signal": {"state": signal_state, "stages": signal},
        "jobs": jobs.all(),
    }


@app.post("/api/ask")
def ask_endpoint(request: AskRequest) -> dict[str, Any]:
    global _active_queries
    db, workspace, llm = runtime()
    if not (workspace.root / "manifest.yaml").exists():
        raise HTTPException(status_code=409, detail="Run Surveyor before asking questions")
    with _signal_lock:
        _active_queries += 1
    _set_signal("reason", "running", "routing, EXPLAIN and execution")
    result: dict[str, Any] | None = None
    try:
        result = ask(db, workspace, request.question, llm)
    finally:
        with _signal_lock:
            _active_queries -= 1
        if result is None or result.get("error"):
            _set_signal("reason", "error", "query failed")
        else:
            _set_signal("reason", "ready", "Query Agent ready")
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    if result.get("explain"):
        result["explain"] = {key: result["explain"].get(key) for key in ("total_cost", "actual_ms", "rows")}
    return result


@app.get("/api/llm/models")
def llm_models() -> dict[str, Any]:
    """Return models from the configured provider on demand; this endpoint is never polled."""
    if settings.llm_provider not in {"opencode_go", "litellm"}:
        return {
            "provider": settings.llm_provider,
            "models": [{"id": settings.active_llm_model, "owned_by": settings.llm_provider}],
        }
    try:
        client = build_llm(
            provider=settings.llm_provider,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            opencode_go_base_url=settings.opencode_go_base_url,
            opencode_go_api_key=settings.opencode_go_api_key,
            opencode_go_model=settings.opencode_go_model,
            litellm_base_url=settings.litellm_base_url,
            litellm_api_key=settings.litellm_api_key,
            litellm_model=settings.litellm_model,
            cache_dir=Workspace(settings.workspace_path).root / ".cache" / "llm",
        )
        if not isinstance(client, OpenCodeGoClient):
            raise LLMUnavailable(f"{settings.llm_provider} provider does not expose a model catalog")
        return {"provider": settings.llm_provider, "models": client.list_models()}
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _start_job(name: str, operation: Callable[[], Any]) -> dict[str, str]:
    try:
        return {"job_id": jobs.start(name, operation), "status": "started"}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/survey")
def survey_endpoint() -> dict[str, str]:
    db, workspace, llm = runtime()
    return _start_job("survey", _tracked_operation("ingest", lambda: run_survey(db, workspace, llm)))


@app.post("/api/explore")
def explore_endpoint() -> dict[str, str]:
    db, workspace, llm = runtime()
    if not (workspace.root / "manifest.yaml").exists():
        raise HTTPException(status_code=409, detail="Run Surveyor before exploring")

    def operation() -> dict[str, Any]:
        result = run_exploration(
            db,
            workspace,
            llm,
            rounds=settings.explorer_rounds,
            probes_per_round=settings.explorer_probes_per_round,
        )
        return {"status": f"{result['rounds_run']} rounds, {len(result['written'])} artifacts", **result}

    return _start_job("explore", _tracked_operation("ingest", operation))


@app.post("/api/evaluate")
def evaluate_endpoint() -> dict[str, str]:
    db, workspace, llm = runtime()
    corpus = default_corpus_path(workspace, settings.project_root)
    return _start_job("evaluate", _tracked_operation("promote", lambda: evaluate_workspace(db, workspace, corpus, llm).as_dict(), "evaluated"))


@app.post("/api/verify")
def verify_endpoint() -> dict[str, str]:
    db, workspace, _ = runtime()
    if not (workspace.root / "manifest.yaml").exists():
        raise HTTPException(status_code=409, detail="Run Surveyor before verifying")
    return _start_job("verify", lambda: verify_skill(db, workspace))


@app.post("/api/optimize")
def optimize_endpoint() -> dict[str, str]:
    """One-click skill improvement: probe the database, then learn from query trajectories."""

    db, workspace, llm = runtime()
    if not (workspace.root / "manifest.yaml").exists():
        raise HTTPException(status_code=409, detail="Run Surveyor before optimizing")

    def operation() -> dict[str, Any]:
        from sqlagent.explorer import optimize_skill

        optimization = optimize_skill(
            db,
            workspace,
            llm,
            rounds_per_domain=1,
            probes_per_round=settings.explorer_probes_per_round,
        )
        try:
            evolution = run_evolution(workspace, llm=llm)
        except Exception as exc:  # no trajectories yet etc. — exploration results still stand
            evolution = {"status": "skipped", "reason": str(exc)[:200]}
        return {**optimization, "evolution": evolution}

    return _start_job("optimize", _tracked_operation("learn", operation))


@app.post("/api/evolve")
def evolve_endpoint() -> dict[str, str]:
    _, workspace, llm = runtime()
    return _start_job("evolve", _tracked_operation("learn", lambda: run_evolution(workspace, llm=llm), "candidate"))


@app.post("/api/promote")
def promote_endpoint() -> dict[str, str]:
    db, workspace, llm = runtime()
    corpus = default_corpus_path(workspace, settings.project_root)
    return _start_job(
        "promote",
        _tracked_operation("promote", lambda: promote_candidate(db, workspace, corpus, None, llm), "promoted"),
    )


def _periodic_verification() -> None:
    """Re-validate skill templates on a timer so stale knowledge is marked failing."""

    interval_hours = settings.verify_interval_hours
    if interval_hours <= 0:
        return

    def loop() -> None:
        import time

        time.sleep(min(300.0, interval_hours * 3600))  # let bootstrap settle, then baseline
        while True:
            try:
                db, workspace, _ = runtime()
                if (workspace.root / "manifest.yaml").exists():
                    verify_skill(db, workspace)
            except Exception:
                pass  # the next tick retries; verification must never take the API down
            time.sleep(interval_hours * 3600)

    threading.Thread(target=loop, name="sqlagent-verify", daemon=True).start()


_periodic_verification()


@app.get("/api/jobs/{job_id}")
def job_endpoint(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
