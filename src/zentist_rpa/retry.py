from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from zentist_rpa.exceptions import TransientPortalError

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover - playwright may be unavailable during static import checks
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]

T = TypeVar("T")


class RetryPolicy:
    def __init__(self, attempts: int, backoff_seconds: float) -> None:
        self.attempts = max(1, attempts)
        self.backoff_seconds = backoff_seconds

    def run(self, label: str, func: Callable[[], T], logger: logging.Logger) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                return func()
            except (TransientPortalError, TimeoutError, PlaywrightTimeoutError) as exc:
                last_error = exc
                logger.warning(
                    "retryable_step_failed",
                    extra={
                        "_rpa": {
                            "step": label,
                            "attempt": attempt,
                            "max_attempts": self.attempts,
                        }
                    },
                )
                if attempt < self.attempts:
                    time.sleep(self.backoff_seconds * attempt)
        assert last_error is not None
        raise last_error
