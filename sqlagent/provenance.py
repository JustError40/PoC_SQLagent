from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProvenanceRecord:
    artifact_id: str
    artifact_path: str
    artifact_hash: str
    run_id: str
    request_id: str
    trajectory_id: str | None
    base_sha: str
    candidate_sha: str
    attribution: str
    source_error: dict[str, Any]
    evidence_sql_hashes: list[str]
    evidence_result_hashes: list[str]
    provider: str | None
    model: str | None
    llm_call_ids: list[str]
    prompt_hashes: list[str]
    schema_hashes: list[str]
    db_snapshot: str
    evaluator_report: str
    promotion_commit: str

    @classmethod
    def build(cls, *, artifact_path: Path, **metadata: Any) -> "ProvenanceRecord":
        content = artifact_path.read_bytes()
        return cls(
            artifact_id=str(metadata.pop("artifact_id", uuid.uuid4().hex)),
            artifact_path=str(artifact_path),
            artifact_hash=hashlib.sha256(content).hexdigest(),
            **metadata,
        )

    def validate_complete(self) -> None:
        missing = [
            field
            for field in (
                "artifact_id",
                "artifact_path",
                "artifact_hash",
                "run_id",
                "request_id",
                "base_sha",
                "candidate_sha",
                "attribution",
                "db_snapshot",
                "evaluator_report",
                "promotion_commit",
            )
            if not getattr(self, field)
        ]
        if missing:
            raise ValueError("incomplete provenance record: " + ", ".join(missing))


class ProvenanceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def write_immutable(self, record: ProvenanceRecord) -> Path:
        record.validate_complete()
        target = self.root / f"{record.artifact_id}.json"
        payload = json.dumps(asdict(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        try:
            os.write(descriptor, payload.encode())
        finally:
            os.close(descriptor)
        return target
