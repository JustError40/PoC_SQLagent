from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator


@dataclass
class Span:
    id: str
    kind: str
    name: str
    started_at: float
    latency_ms: float | None = None
    status: str = "running"
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Trace:
    request_id: str
    spans: list[Span] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "spans": [span.as_dict() for span in self.spans]}


_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar("sqlagent_trace", default=None)


@contextlib.contextmanager
def trace_context(request_id: str | None = None) -> Iterator[Trace]:
    trace = Trace(request_id=request_id or uuid.uuid4().hex)
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


@contextlib.contextmanager
def span(kind: str, name: str, **attributes: Any) -> Iterator[Span]:
    item = Span(
        id=uuid.uuid4().hex[:16],
        kind=kind,
        name=name,
        started_at=time.time(),
        attributes=dict(attributes),
    )
    trace = _current_trace.get()
    if trace is not None:
        trace.spans.append(item)
    started = time.perf_counter()
    try:
        yield item
    except BaseException as exc:
        item.status = "error"
        item.attributes.setdefault("error", str(exc)[:500])
        raise
    else:
        item.status = "ok"
    finally:
        item.latency_ms = round((time.perf_counter() - started) * 1000, 3)


def current_trace() -> Trace | None:
    return _current_trace.get()
