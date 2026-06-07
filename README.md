<!-- schema-ref: zentist-r7 -->
# Zentist RPA Lead Test Task

Python 3.11+ implementation of a shared RPA foundation for two portals:

- OrangeHRM: employee lookup/create, Job section update, Salary attachment upload.
- Sauce Demo: full checkout attempt for every required account with per-account outcomes.

The project is intentionally structured as a small production-style platform: portal runners only know
portal-specific selectors and flows, while persistence, reports, e-mail, retry, metrics, artifacts and
batch isolation are shared.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Configure secrets and runtime locations outside the code:

```powershell
$env:ORANGE_USERNAME="Admin"
$env:ORANGE_PASSWORD="admin123"
$env:SAUCE_PASSWORD="secret_sauce"
$env:RPA_EMAIL_RECIPIENT="ops@example.com"
$env:RPA_DB_PATH="var/zentist_rpa.sqlite"
$env:RPA_REPORT_DIR="var/reports"
$env:RPA_ARTIFACT_DIR="var/artifacts"
```

Run both portals:

```powershell
zentist-rpa --portal all --employees samples/employees.json
```

Run one portal:

```powershell
zentist-rpa --portal sauce
zentist-rpa --portal orange --employees samples/employees.json
```

If SMTP is not configured, the report e-mail is written to `var/reports/outbox/*.eml`. This keeps local
runs testable without storing SMTP credentials in the repository.

## Configuration

All operational configuration is read from environment variables or an optional JSON file passed with
`--config`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `ORANGE_USERNAME` / `ORANGE_PASSWORD` | OrangeHRM credentials | none |
| `SAUCE_PASSWORD` | Sauce Demo password for all accounts | none |
| `RPA_DB_PATH` | SQLite database path | `var/zentist_rpa.sqlite` |
| `RPA_REPORT_DIR` | Markdown report and e-mail spool directory | `var/reports` |
| `RPA_ARTIFACT_DIR` | Generated salary/order artifacts | `var/artifacts` |
| `RPA_EMAIL_RECIPIENT` | Report recipient | none |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | SMTP delivery | spool mode |
| `RPA_HEADLESS` | Browser headless mode | `true` |
| `RPA_TIMEOUT_MS` | Playwright default timeout | `15000` |
| `RPA_MAX_RETRIES` | Retry count after first attempt | `2` |
| `RPA_BUSINESS_DATE` | Idempotency date override | today |

Credentials are never logged in plaintext. `config.redacted()` masks username/password fields in
structured logs.

## Input Format

OrangeHRM input lives in `samples/employees.json`:

```json
{
  "employees": [
    {
      "first_name": "Alex",
      "last_name": "Zentist",
      "employee_id": "ZX-1001",
      "job_title": "QA Engineer",
      "employment_status": "Full-Time Permanent",
      "salary_amount": "90000"
    }
  ]
}
```

`employee_id` is the idempotency key for OrangeHRM. Sauce Demo processes the six required accounts from
the PDF: `standard_user`, `locked_out_user`, `problem_user`, `performance_glitch_user`, `error_user`,
and `visual_user`.

## Persistence and Idempotency

SQLite stores two tables:

- `runs`: one row per portal run.
- `outcomes`: one row per `business_date + portal + item_key`.

`outcomes` uses an upsert primary key, so same-day reruns update the latest outcome instead of appending
duplicates. This means a failed first attempt can be replaced by a later success, and reports stay
coherent.

OrangeHRM also behaves idempotently in the portal itself:

- Existing employees are found by `employee_id`.
- Missing employees are added once.
- Job Title and Employment Status are refreshed every run.
- Salary attachment is uploaded only when the expected attachment is absent.

## Adding a Portal

Add a third portal without changing the first two:

1. Create `src/zentist_rpa/portals/<portal>.py`.
2. Subclass `BasePortalRunnerZX`.
3. Implement `open_session`, `item_key`, and `process_item`.
4. Use shared connectors from the base class: `self.db`, `self.artifacts`, `self.retry`.
5. Wire the runner into `src/zentist_rpa/cli.py` or a scheduler entrypoint.

Portal code should contain only portal-specific login, navigation, selectors and business actions.
Retries, metrics, reports, e-mail and persistence belong in shared modules.

## Tests and CI

Local checks:

```powershell
ruff check .
pytest -q
```

GitHub Actions runs on PRs and pushes to `master`/`main`:

- install Python 3.11 dependencies
- install Chromium for Playwright
- run `ruff check .`
- run `pytest -q`

Tests avoid live demo portals by design. They cover shared behavior that must remain stable in CI:
idempotent database upserts, batch continuation after item failures, setup-failure reporting for every
unprocessed item, retry handling, report generation and e-mail spooling.
