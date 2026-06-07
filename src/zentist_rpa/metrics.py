from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class RunMetrics:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    started_at: float = field(default_factory=monotonic)

    def observe(self, status: str) -> None:
        self.total += 1
        if status == "success":
            self.succeeded += 1
        elif status == "skipped":
            self.skipped += 1
        else:
            self.failed += 1

    @property
    def elapsed_seconds(self) -> float:
        return monotonic() - self.started_at
