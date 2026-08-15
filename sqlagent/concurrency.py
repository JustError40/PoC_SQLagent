from __future__ import annotations

import contextlib
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class LimiterSnapshot:
    limit: int
    in_flight: int
    stable_successes: int
    reductions: int


class AdaptiveLimiter:
    """Priority-aware 1..12 limiter with AIMD feedback.

    Priority 0 is interactive traffic. Background learner calls should use 10.
    The limit is cut in half on 429/timeouts/pool saturation and grows by one
    after a configurable stable window.
    """

    def __init__(
        self,
        initial: int = 12,
        minimum: int = 1,
        maximum: int = 12,
        stable_window: int = 8,
    ) -> None:
        if not (1 <= minimum <= initial <= maximum <= 12):
            raise ValueError("adaptive limiter requires 1 <= min <= initial <= max <= 12")
        self.minimum = minimum
        self.maximum = maximum
        self.stable_window = max(1, stable_window)
        self._limit = initial
        self._in_flight = 0
        self._successes = 0
        self._reductions = 0
        self._sequence = 0
        self._waiters: deque[tuple[int, int]] = deque()
        self._condition = threading.Condition()

    @property
    def limit(self) -> int:
        with self._condition:
            return self._limit

    def acquire(self, priority: int = 0, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            self._sequence += 1
            waiter = (priority, self._sequence)
            self._waiters.append(waiter)
            try:
                while True:
                    selected = min(self._waiters) if self._waiters else None
                    if selected == waiter and self._in_flight < self._limit:
                        self._waiters.remove(waiter)
                        self._in_flight += 1
                        return
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise TimeoutError("adaptive limiter acquisition timed out")
                    self._condition.wait(remaining)
            except BaseException:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
                self._condition.notify_all()
                raise

    def release(self) -> None:
        with self._condition:
            if self._in_flight <= 0:
                raise RuntimeError("adaptive limiter released without acquire")
            self._in_flight -= 1
            self._condition.notify_all()

    def record_success(self) -> None:
        with self._condition:
            self._successes += 1
            if self._successes >= self.stable_window and self._limit < self.maximum:
                self._limit += 1
                self._successes = 0
                self._condition.notify_all()

    def record_pressure(self) -> None:
        with self._condition:
            self._limit = max(self.minimum, self._limit // 2)
            self._successes = 0
            self._reductions += 1
            self._condition.notify_all()

    def snapshot(self) -> LimiterSnapshot:
        with self._condition:
            return LimiterSnapshot(self._limit, self._in_flight, self._successes, self._reductions)

    @contextlib.contextmanager
    def slot(self, priority: int = 0, timeout: float | None = None) -> Iterator[None]:
        self.acquire(priority=priority, timeout=timeout)
        try:
            yield
        except BaseException as exc:
            text = str(exc).lower()
            if any(marker in text for marker in ("429", "timeout", "timed out", "pool", "saturation")):
                self.record_pressure()
            raise
        else:
            self.record_success()
        finally:
            self.release()


def _initial(name: str) -> int:
    try:
        return max(1, min(12, int(os.getenv(name, "12"))))
    except ValueError:
        return 12


LITELLM_LIMITER = AdaptiveLimiter(initial=_initial("LLM_CONCURRENCY_INITIAL"))
POSTGRES_LIMITER = AdaptiveLimiter(initial=_initial("DB_CONCURRENCY_INITIAL"))
