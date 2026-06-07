from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from zentist_rpa.config import AppConfig
from zentist_rpa.connectors.artifacts import ArtifactConnector
from zentist_rpa.connectors.db import DatabaseConnector
from zentist_rpa.connectors.email import EmailConnector
from zentist_rpa.connectors.report import ReportConnector
from zentist_rpa.logging import configure_logging
from zentist_rpa.models import EmployeeInput, SauceAccountInput
from zentist_rpa.portals.orange_hrm import OrangeHrmRunner
from zentist_rpa.portals.sauce_demo import SAUCE_ACCOUNTS, SauceDemoRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Zentist RPA portal automations.")
    parser.add_argument("--portal", choices=["all", "orange", "sauce"], default="all")
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional JSON config file. Env vars are preferred.",
    )
    parser.add_argument("--employees", type=Path, default=Path("samples/employees.json"))
    parser.add_argument("--business-date", help="Override YYYY-MM-DD business date.")
    args = parser.parse_args(argv)

    configure_logging()
    logger = logging.getLogger("zentist_rpa.cli")
    config = AppConfig.from_json_file(args.config) if args.config else AppConfig.from_env()
    business_date = _business_date(args.business_date or config.business_date)
    logger.info("config_loaded", extra={"_rpa": {"config": config.redacted()}})

    db = DatabaseConnector(config.db_path)
    artifacts = ArtifactConnector(config.artifact_dir)
    metrics_by_portal = {}

    if args.portal in {"all", "orange"}:
        employees = load_employees(args.employees)
        metrics_by_portal["orange_hrm"] = OrangeHrmRunner(
            config=config,
            db=db,
            artifacts=artifacts,
        ).run(employees, business_date=business_date)

    if args.portal in {"all", "sauce"}:
        if not config.sauce_password:
            raise SystemExit("SAUCE_PASSWORD must be configured outside the code")
        accounts = [
            SauceAccountInput(username=name, password=config.sauce_password)
            for name in SAUCE_ACCOUNTS
        ]
        metrics_by_portal["sauce_demo"] = SauceDemoRunner(
            config=config,
            db=db,
            artifacts=artifacts,
        ).run(accounts, business_date=business_date)

    report_path = ReportConnector(config.report_dir, db).generate_daily_report(business_date)
    spool_path = EmailConnector(
        recipient=config.email_recipient,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_username=config.smtp_username,
        smtp_password=config.smtp_password,
        sender=config.smtp_from,
        spool_dir=config.report_dir / "outbox",
    ).send_report(
        subject=f"Zentist RPA Daily Report {business_date.isoformat()}",
        body=f"Daily report generated at {report_path}",
        attachment=report_path,
    )

    logger.info(
        "daily_report_ready",
        extra={
            "_rpa": {
                "business_date": business_date.isoformat(),
                "report_path": str(report_path),
                "email_spool_path": str(spool_path) if spool_path else None,
                "metrics": {
                    portal: {
                        "total": metrics.total,
                        "succeeded": metrics.succeeded,
                        "failed": metrics.failed,
                        "skipped": metrics.skipped,
                    }
                    for portal, metrics in metrics_by_portal.items()
                },
            }
        },
    )
    return 0


def _business_date(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def load_employees(path: Path) -> list[EmployeeInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [EmployeeInput(**row) for row in payload["employees"]]


if __name__ == "__main__":
    raise SystemExit(main())
