from __future__ import annotations

from datetime import date

from zentist_rpa.connectors.db import DatabaseConnector
from zentist_rpa.connectors.email import EmailConnector
from zentist_rpa.connectors.report import ReportConnector
from zentist_rpa.models import OutcomeStatus, WorkItemResult


def test_outcome_upsert_is_idempotent_for_same_business_day(tmp_path):
    db = DatabaseConnector(tmp_path / "rpa.sqlite")
    business_date = date(2026, 6, 6)
    db.start_run("run-1", "sauce_demo", business_date)
    db.upsert_outcome(
        business_date=business_date,
        portal="sauce_demo",
        run_id="run-1",
        result=WorkItemResult(
            item_key="standard_user",
            status=OutcomeStatus.FAILURE,
            reason="first attempt failed",
        ),
    )

    db.start_run("run-2", "sauce_demo", business_date)
    db.upsert_outcome(
        business_date=business_date,
        portal="sauce_demo",
        run_id="run-2",
        result=WorkItemResult(
            item_key="standard_user",
            status=OutcomeStatus.SUCCESS,
            reason="recovered",
            details={"order": "ok"},
        ),
    )

    outcomes = db.fetch_daily_outcomes(business_date)
    assert len(outcomes) == 1
    assert outcomes[0]["run_id"] == "run-2"
    assert outcomes[0]["status"] == "success"
    assert outcomes[0]["reason"] == "recovered"


def test_report_and_email_spool_are_generated(tmp_path):
    db = DatabaseConnector(tmp_path / "rpa.sqlite")
    business_date = date(2026, 6, 6)
    db.start_run("run-1", "orange_hrm", business_date)
    db.upsert_outcome(
        business_date=business_date,
        portal="orange_hrm",
        run_id="run-1",
        result=WorkItemResult(
            item_key="ZX-1001",
            status=OutcomeStatus.SUCCESS,
            reason="employee_up_to_date",
            artifact_path=tmp_path / "salary.txt",
        ),
    )

    report = ReportConnector(tmp_path / "reports", db).generate_daily_report(business_date)
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Zentist RPA Daily Report" in text
    assert "ZX-1001" in text

    spool = EmailConnector(
        recipient=None,
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        sender="bot@example.invalid",
        spool_dir=tmp_path / "outbox",
    ).send_report(subject="report", body="body", attachment=report)

    assert spool is not None
    assert spool.exists()
    assert b"Subject: report" in spool.read_bytes()
