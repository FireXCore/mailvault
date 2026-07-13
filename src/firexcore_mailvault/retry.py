from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryPolicy:
    def __init__(self, max_attempts: int) -> None:
        self.max_attempts = max_attempts

    def run(
        self,
        operation: Callable[[], T],
        *,
        on_retry: Callable[[BaseException, int, float], None] | None = None,
        retryable: Callable[[BaseException], bool] | None = None,
    ) -> T:
        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except BaseException as exc:
                last_error = exc
                if retryable is not None and not retryable(exc):
                    raise
                if attempt >= self.max_attempts:
                    raise
                base = min(900.0, 15.0 * (2 ** (attempt - 1)))
                delay = random.uniform(base * 0.5, base * 1.5)
                if on_retry:
                    on_retry(exc, attempt, delay)
                time.sleep(delay)
        assert last_error is not None
        raise last_error
