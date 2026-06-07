from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from zentist_rpa.connectors.db import DatabaseConnector


class ReportConnector:
    def __init__(self, report_dir: Path, db: DatabaseConnector) -> None:
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.db = db

    def generate_daily_report(self, business_date: date) -> Path:
        outcomes = self.db.fetch_daily_outcomes(business_date)
        counts = Counter(row["status"] for row in outcomes)
        lines = [
            f"# Zentist RPA Daily Report - {business_date.isoformat()}",
            "",
            "## Summary",
            "",
            f"- Total items: {len(outcomes)}",
            f"- Success: {counts.get('success', 0)}",
            f"- Failure: {counts.get('failure', 0)}",
            f"- Skipped: {counts.get('skipped', 0)}",
            "",
            "## Item Outcomes",
            "",
            "| Portal | Item | Status | Reason | Artifact |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in outcomes:
            reason = row["reason"].replace("|", "\\|")
            artifact = row["artifact_path"] or ""
            lines.append(
                f"| {row['portal']} | {row['item_key']} | {row['status']} | {reason} | {artifact} |"
            )
        lines.append("")
        report_path = self.report_dir / f"{business_date.isoformat()}_daily_report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
