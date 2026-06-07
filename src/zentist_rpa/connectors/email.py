from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path


class EmailConnector:
    def __init__(
        self,
        *,
        recipient: str | None,
        smtp_host: str | None,
        smtp_port: int,
        smtp_username: str | None,
        smtp_password: str | None,
        sender: str,
        spool_dir: Path,
    ) -> None:
        self.recipient = recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.sender = sender
        self.spool_dir = spool_dir
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def send_report(self, *, subject: str, body: str, attachment: Path) -> Path | None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = self.recipient or "not-configured@example.invalid"
        message["Subject"] = subject
        message.set_content(body)
        message.add_attachment(
            attachment.read_bytes(),
            maintype="text",
            subtype="markdown",
            filename=attachment.name,
        )

        if self.smtp_host and self.recipient:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if self.smtp_username and self.smtp_password:
                    smtp.login(self.smtp_username, self.smtp_password)
                smtp.send_message(message)
            return None

        spool_path = self.spool_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_report.eml"
        spool_path.write_bytes(message.as_bytes())
        return spool_path
