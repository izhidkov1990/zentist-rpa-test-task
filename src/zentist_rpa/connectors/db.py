from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from zentist_rpa.models import OutcomeStatus, WorkItemResult


class DatabaseConnector:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    portal TEXT NOT NULL,
                    business_date TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    succeeded INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS outcomes (
                    business_date TEXT NOT NULL,
                    portal TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    artifact_path TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (business_date, portal, item_key)
                );
                """
            )

    def start_run(self, run_id: str, portal: str, business_date: date) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, portal, business_date, started_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, portal, business_date.isoformat(), now, "running"),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        total: int,
        succeeded: int,
        failed: int,
        skipped: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, total = ?, succeeded = ?, failed = ?, skipped = ?
                WHERE run_id = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    status,
                    total,
                    succeeded,
                    failed,
                    skipped,
                    run_id,
                ),
            )

    def upsert_outcome(
        self,
        *,
        business_date: date,
        portal: str,
        run_id: str,
        result: WorkItemResult,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outcomes (
                    business_date, portal, item_key, run_id, status, reason,
                    details_json, artifact_path, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(business_date, portal, item_key) DO UPDATE SET
                    run_id = excluded.run_id,
                    status = excluded.status,
                    reason = excluded.reason,
                    details_json = excluded.details_json,
                    artifact_path = excluded.artifact_path,
                    updated_at = excluded.updated_at
                """,
                (
                    business_date.isoformat(),
                    portal,
                    result.item_key,
                    run_id,
                    result.status.value,
                    result.reason,
                    json.dumps(result.details, ensure_ascii=False, sort_keys=True),
                    str(result.artifact_path) if result.artifact_path else None,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def fetch_daily_outcomes(self, business_date: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT business_date, portal, item_key, run_id, status, reason,
                       details_json, artifact_path, updated_at
                FROM outcomes
                WHERE business_date = ?
                ORDER BY portal, item_key
                """,
                (business_date.isoformat(),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count_outcomes(self, business_date: date) -> dict[str, int]:
        counts = {status.value: 0 for status in OutcomeStatus}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM outcomes
                WHERE business_date = ?
                GROUP BY status
                """,
                (business_date.isoformat(),),
            ).fetchall()
        for row in rows:
            counts[row["status"]] = row["count"]
        return counts

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["details"] = json.loads(payload.pop("details_json"))
        return payload

    def known_successful_items(
        self, *, business_date: date, portal: str, item_keys: Iterable[str]
    ) -> set[str]:
        keys = list(item_keys)
        if not keys:
            return set()
        placeholders = ",".join("?" for _ in keys)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT item_key FROM outcomes
                WHERE business_date = ?
                  AND portal = ?
                  AND status = 'success'
                  AND item_key IN ({placeholders})
                """,
                [business_date.isoformat(), portal, *keys],
            ).fetchall()
        return {row["item_key"] for row in rows}
