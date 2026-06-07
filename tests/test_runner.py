from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from zentist_rpa.config import AppConfig
from zentist_rpa.connectors.artifacts import ArtifactConnector
from zentist_rpa.connectors.db import DatabaseConnector
from zentist_rpa.exceptions import PortalBusinessError, TransientPortalError
from zentist_rpa.models import OutcomeStatus, RunContext, WorkItemResult
from zentist_rpa.portals.base import BasePortalRunnerZX


class FakeRunner(BasePortalRunnerZX[str, object]):
    portal_name = "fake"

    def __init__(self, *args, fail_business: set[str] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail_business = fail_business or set()
        self.transient_attempts = 0

    @contextmanager
    def open_session(self, run_context: RunContext) -> Iterator[object]:
        yield object()

    def item_key(self, item: str) -> str:
        return item

    def process_item(
        self, session: object, run_context: RunContext, item: str
    ) -> WorkItemResult:
        if item in self.fail_business:
            raise PortalBusinessError(f"{item} rejected")
        if item == "flaky" and self.transient_attempts == 0:
            self.transient_attempts += 1
            raise TransientPortalError("temporary portal timeout")
        return WorkItemResult(item_key=item, status=OutcomeStatus.SUCCESS, reason="ok")


class SetupFailureRunner(FakeRunner):
    @contextmanager
    def open_session(self, run_context: RunContext) -> Iterator[object]:
        raise RuntimeError("browser could not start")
        yield object()


def config(tmp_path) -> AppConfig:
    return AppConfig.from_env(
        {
            "RPA_DB_PATH": str(tmp_path / "rpa.sqlite"),
            "RPA_REPORT_DIR": str(tmp_path / "reports"),
            "RPA_ARTIFACT_DIR": str(tmp_path / "artifacts"),
            "RPA_MAX_RETRIES": "1",
            "RPA_RETRY_BACKOFF_SECONDS": "0",
        }
    )


def test_runner_continues_after_item_failure(tmp_path):
    cfg = config(tmp_path)
    db = DatabaseConnector(cfg.db_path)
    runner = FakeRunner(
        config=cfg,
        db=db,
        artifacts=ArtifactConnector(cfg.artifact_dir),
        fail_business={"bad"},
    )

    metrics = runner.run(["ok", "bad", "next"], business_date=date(2026, 6, 6))

    assert metrics.total == 3
    assert metrics.succeeded == 2
    assert metrics.failed == 1
    outcomes = {row["item_key"]: row for row in db.fetch_daily_outcomes(date(2026, 6, 6))}
    assert outcomes["bad"]["status"] == "failure"
    assert outcomes["next"]["status"] == "success"


def test_runner_records_unprocessed_items_on_setup_failure(tmp_path):
    cfg = config(tmp_path)
    db = DatabaseConnector(cfg.db_path)
    runner = SetupFailureRunner(
        config=cfg,
        db=db,
        artifacts=ArtifactConnector(cfg.artifact_dir),
    )

    metrics = runner.run(["one", "two"], business_date=date(2026, 6, 6))

    assert metrics.total == 2
    assert metrics.failed == 2
    outcomes = db.fetch_daily_outcomes(date(2026, 6, 6))
    assert {row["item_key"] for row in outcomes} == {"one", "two"}
    assert all(row["status"] == "failure" for row in outcomes)


def test_transient_failures_are_retried(tmp_path):
    cfg = config(tmp_path)
    db = DatabaseConnector(cfg.db_path)
    runner = FakeRunner(
        config=cfg,
        db=db,
        artifacts=ArtifactConnector(cfg.artifact_dir),
    )

    metrics = runner.run(["flaky"], business_date=date(2026, 6, 6))

    assert metrics.succeeded == 1
    assert runner.transient_attempts == 1
