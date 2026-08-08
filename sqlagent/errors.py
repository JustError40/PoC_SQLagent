from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    LLM_TIMEOUT = "llm_timeout"
    LLM_TRANSPORT_ERROR = "llm_transport_error"
    LLM_INVALID_JSON = "llm_invalid_json"
    LLM_SCHEMA_VIOLATION = "llm_schema_violation"
    SCHEMA_SELECTION_FAILED = "schema_selection_failed"
    PLAN_ASSEMBLY_FAILED = "plan_assembly_failed"
    SQL_VALIDATION_FAILED = "sql_validation_failed"
    EXPLAIN_TIMEOUT = "explain_timeout"
    EXECUTION_TIMEOUT = "execution_timeout"
    DB_ERROR = "db_error"
    CRITIC_REJECTED = "critic_rejected"
    REACT_EXHAUSTED = "react_exhausted"
    LANGGRAPH_RECURSION = "langgraph_recursion"
    SERIALIZATION_FAILED = "serialization_failed"
    WORKSPACE_ERROR = "workspace_error"
    INTERNAL_ERROR = "internal_error"


RETRYABLE_ERRORS = {
    ErrorType.LLM_TIMEOUT,
    ErrorType.LLM_TRANSPORT_ERROR,
    ErrorType.EXPLAIN_TIMEOUT,
    ErrorType.EXECUTION_TIMEOUT,
    ErrorType.DB_ERROR,
    ErrorType.SERIALIZATION_FAILED,
}


@dataclass(frozen=True)
class AgentError:
    type: ErrorType
    stage: str
    retryable: bool
    message: str
    sqlstate: str | None = None
    learning_job_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = self.type.value
        return payload


class AgentFailure(RuntimeError):
    def __init__(self, error: AgentError) -> None:
        super().__init__(error.message)
        self.error = error


def error_type_for_message(message: str, stage: str = "internal") -> ErrorType:
    text = message.lower()
    if "schema selection" in text:
        return ErrorType.SCHEMA_SELECTION_FAILED
    if "schema violation" in text:
        return ErrorType.LLM_SCHEMA_VIOLATION
    if "invalid json" in text or "jsondecode" in text:
        return ErrorType.LLM_INVALID_JSON
    if "serialization" in text or stage == "serialization":
        return ErrorType.SERIALIZATION_FAILED
    if stage == "workspace" or "workspace" in text:
        return ErrorType.WORKSPACE_ERROR
    if "recursion" in text:
        return ErrorType.LANGGRAPH_RECURSION
    if "budget exhausted" in text:
        return ErrorType.REACT_EXHAUSTED
    if "critic rejected" in text:
        return ErrorType.CRITIC_REJECTED
    if "assembly failed" in text or "plan assembly" in text:
        return ErrorType.PLAN_ASSEMBLY_FAILED
    if "lint failed" in text or "read-only" in text or "only read" in text:
        return ErrorType.SQL_VALIDATION_FAILED
    if "json" in text and ("invalid" in text or "decode" in text or "did not return" in text):
        return ErrorType.LLM_INVALID_JSON
    if "schema" in text and ("validation" in text or "violation" in text):
        return ErrorType.LLM_SCHEMA_VIOLATION
    if "timeout" in text or "timed out" in text:
        if stage.startswith("llm") or "model" in text:
            return ErrorType.LLM_TIMEOUT
        if stage.startswith("explain"):
            return ErrorType.EXPLAIN_TIMEOUT
        if stage in {"execute", "execution", "db"}:
            return ErrorType.EXECUTION_TIMEOUT
    if stage.startswith("llm"):
        return ErrorType.LLM_TRANSPORT_ERROR
    if stage in {"execute", "execution", "explain", "db"}:
        return ErrorType.DB_ERROR
    return ErrorType.INTERNAL_ERROR


def classify_error(
    exc: BaseException | str,
    *,
    stage: str,
    learning_job_id: str | None = None,
) -> AgentError:
    message = str(exc)
    class_name = type(exc).__name__.lower() if not isinstance(exc, str) else ""
    if "timeout" in class_name:
        error_type = error_type_for_message("timeout", stage)
    elif "schema" in class_name and stage.startswith("llm"):
        error_type = ErrorType.LLM_SCHEMA_VIOLATION
    elif "json" in class_name and stage.startswith("llm"):
        error_type = ErrorType.LLM_INVALID_JSON
    else:
        error_type = error_type_for_message(message, stage)
    sqlstate = getattr(exc, "sqlstate", None)
    return AgentError(
        type=error_type,
        stage=stage,
        retryable=error_type in RETRYABLE_ERRORS,
        message=message[:1000],
        sqlstate=str(sqlstate) if sqlstate else None,
        learning_job_id=learning_job_id,
    )
