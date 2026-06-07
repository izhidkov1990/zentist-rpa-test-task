from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any


class OutcomeStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    portal: str
    business_date: date


@dataclass(frozen=True)
class WorkItemResult:
    item_key: str
    status: OutcomeStatus
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    artifact_path: Path | None = None


@dataclass(frozen=True)
class EmployeeInput:
    first_name: str
    last_name: str
    employee_id: str
    job_title: str
    employment_status: str
    salary_amount: str
    salary_currency: str = "USD"
    middle_name: str = ""

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part).strip()

    @property
    def item_key(self) -> str:
        return self.employee_id


@dataclass(frozen=True)
class SauceAccountInput:
    username: str
    password: str
    first_name: str = "Zentist"
    last_name: str = "Buyer"
    postal_code: str = "10001"
    item_count: int = 3

    @property
    def item_key(self) -> str:
        return self.username
