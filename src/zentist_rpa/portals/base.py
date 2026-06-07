from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Generic, TypeVar

from zentist_rpa.config import AppConfig
from zentist_rpa.connectors.artifacts import ArtifactConnector
from zentist_rpa.connectors.db import DatabaseConnector
from zentist_rpa.exceptions import PortalBusinessError
from zentist_rpa.metrics import RunMetrics
from zentist_rpa.models import OutcomeStatus, RunContext, WorkItemResult
from zentist_rpa.retry import RetryPolicy

TItem = TypeVar("TItem")
TSession = TypeVar("TSession")


class BasePortalRunnerZX(ABC, Generic[TItem, TSession]):
    portal_name: str

    def __init__(
        self,
        *,
        config: AppConfig,
        db: DatabaseConnector,
        artifacts: ArtifactConnector,
        retry: RetryPolicy | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.artifacts = artifacts
        self.retry = retry or RetryPolicy(config.max_retries + 1, config.retry_backoff_seconds)
        self.logger = logger or logging.getLogger(f"zentist_rpa.{self.portal_name}")

    def run(self, items: Iterable[TItem], *, business_date: date) -> RunMetrics:
        item_list = list(items)
        run_context = RunContext(
            run_id=str(uuid.uuid4()),
            portal=self.portal_name,
            business_date=business_date,
        )
        metrics = RunMetrics()
        processed_keys: set[str] = set()
        self.db.start_run(run_context.run_id, self.portal_name, business_date)
        self.logger.info(
            "run_started",
            extra={
                "_rpa": {
                    "run_id": run_context.run_id,
                    "portal": self.portal_name,
                    "item_count": len(item_list),
                }
            },
        )

        status = "success"
        try:
            with self.open_session(run_context) as session:
                self.before_batch(session, run_context)
                for item in item_list:
                    result = self._process_one(session, run_context, item)
                    processed_keys.add(self.item_key(item))
                    metrics.observe(result.status.value)
        except Exception as exc:
            status = "failure"
            self.logger.exception(
                "run_level_failure",
                extra={"_rpa": {"run_id": run_context.run_id, "portal": self.portal_name}},
            )
            for item in item_list:
                item_key = self.item_key(item)
                if item_key in processed_keys:
                    continue
                result = WorkItemResult(
                    item_key=item_key,
                    status=OutcomeStatus.FAILURE,
                    reason=f"run_level_failure: {type(exc).__name__}: {exc}",
                )
                self.db.upsert_outcome(
                    business_date=run_context.business_date,
                    portal=self.portal_name,
                    run_id=run_context.run_id,
                    result=result,
                )
                metrics.observe(result.status.value)
        finally:
            if metrics.failed or status == "failure":
                status = "partial_failure" if metrics.total else "failure"
            self.db.finish_run(
                run_context.run_id,
                status=status,
                total=metrics.total,
                succeeded=metrics.succeeded,
                failed=metrics.failed,
                skipped=metrics.skipped,
            )
            self.logger.info(
                "run_finished",
                extra={
                    "_rpa": {
                        "run_id": run_context.run_id,
                        "portal": self.portal_name,
                        "status": status,
                        "total": metrics.total,
                        "succeeded": metrics.succeeded,
                        "failed": metrics.failed,
                        "skipped": metrics.skipped,
                        "elapsed_seconds": round(metrics.elapsed_seconds, 3),
                    }
                },
            )
        return metrics

    def _process_one(
        self, session: TSession, run_context: RunContext, item: TItem
    ) -> WorkItemResult:
        item_key = self.item_key(item)
        self.logger.info(
            "item_started",
            extra={
                "_rpa": {
                    "run_id": run_context.run_id,
                    "portal": self.portal_name,
                    "item_key": item_key,
                }
            },
        )
        try:
            result = self.retry.run(
                f"{self.portal_name}:{item_key}",
                lambda: self.process_item(session, run_context, item),
                self.logger,
            )
        except PortalBusinessError as exc:
            result = WorkItemResult(
                item_key=item_key,
                status=OutcomeStatus.FAILURE,
                reason=str(exc),
            )
        except Exception as exc:
            self.logger.exception(
                "item_failed",
                extra={
                    "_rpa": {
                        "run_id": run_context.run_id,
                        "portal": self.portal_name,
                        "item_key": item_key,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            result = WorkItemResult(
                item_key=item_key,
                status=OutcomeStatus.FAILURE,
                reason=f"{type(exc).__name__}: {exc}",
            )

        self.db.upsert_outcome(
            business_date=run_context.business_date,
            portal=self.portal_name,
            run_id=run_context.run_id,
            result=result,
        )
        self.logger.info(
            "item_finished",
            extra={
                "_rpa": {
                    "run_id": run_context.run_id,
                    "portal": self.portal_name,
                    "item_key": item_key,
                    "status": result.status.value,
                    "reason": result.reason,
                }
            },
        )
        return result

    def before_batch(self, session: TSession, run_context: RunContext) -> None:
        return None

    @abstractmethod
    def item_key(self, item: TItem) -> str:
        raise NotImplementedError

    @abstractmethod
    def process_item(
        self, session: TSession, run_context: RunContext, item: TItem
    ) -> WorkItemResult:
        raise NotImplementedError

    @contextmanager
    @abstractmethod
    def open_session(self, run_context: RunContext) -> Iterator[TSession]:
        raise NotImplementedError
