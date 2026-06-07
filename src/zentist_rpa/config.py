from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    report_dir: Path
    artifact_dir: Path
    headless: bool
    timeout_ms: int
    max_retries: int
    retry_backoff_seconds: float
    business_date: str | None
    orange_base_url: str
    orange_username: str | None
    orange_password: str | None
    sauce_base_url: str
    sauce_password: str | None
    email_recipient: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AppConfig:
        source = env or os.environ
        return cls(
            db_path=Path(source.get("RPA_DB_PATH", "var/zentist_rpa.sqlite")),
            report_dir=Path(source.get("RPA_REPORT_DIR", "var/reports")),
            artifact_dir=Path(source.get("RPA_ARTIFACT_DIR", "var/artifacts")),
            headless=_bool(source.get("RPA_HEADLESS"), True),
            timeout_ms=int(source.get("RPA_TIMEOUT_MS", "15000")),
            max_retries=int(source.get("RPA_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(source.get("RPA_RETRY_BACKOFF_SECONDS", "0.5")),
            business_date=source.get("RPA_BUSINESS_DATE"),
            orange_base_url=source.get(
                "ORANGE_BASE_URL", "https://opensource-demo.orangehrmlive.com"
            ),
            orange_username=source.get("ORANGE_USERNAME"),
            orange_password=source.get("ORANGE_PASSWORD"),
            sauce_base_url=source.get("SAUCE_BASE_URL", "https://www.saucedemo.com"),
            sauce_password=source.get("SAUCE_PASSWORD"),
            email_recipient=source.get("RPA_EMAIL_RECIPIENT"),
            smtp_host=source.get("SMTP_HOST"),
            smtp_port=int(source.get("SMTP_PORT", "587")),
            smtp_username=source.get("SMTP_USERNAME"),
            smtp_password=source.get("SMTP_PASSWORD"),
            smtp_from=source.get("SMTP_FROM", "zentist-rpa@example.invalid"),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> AppConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        env_like = {key: str(value) for key, value in data.items() if value is not None}
        return cls.from_env(env_like)

    def redacted(self) -> dict[str, Any]:
        payload = self.__dict__.copy()
        for key in list(payload):
            if "password" in key or "username" in key:
                payload[key] = "***" if payload[key] else None
        return payload
