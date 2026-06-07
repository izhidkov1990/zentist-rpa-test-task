from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Locator, Page, sync_playwright

from zentist_rpa.exceptions import PortalBusinessError
from zentist_rpa.models import EmployeeInput, OutcomeStatus, RunContext, WorkItemResult
from zentist_rpa.portals.base import BasePortalRunnerZX


class OrangeHrmRunner(BasePortalRunnerZX[EmployeeInput, Page]):
    portal_name = "orange_hrm"

    @contextmanager
    def open_session(self, run_context: RunContext) -> Iterator[Page]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.config.timeout_ms)
            try:
                yield page
            finally:
                context.close()
                browser.close()

    def before_batch(self, session: Page, run_context: RunContext) -> None:
        if not self.config.orange_username or not self.config.orange_password:
            raise PortalBusinessError("OrangeHRM credentials are not configured")
        self._login(session)

    def item_key(self, item: EmployeeInput) -> str:
        return item.item_key

    def process_item(
        self, session: Page, run_context: RunContext, item: EmployeeInput
    ) -> WorkItemResult:
        page = session
        created = False
        if not self._open_employee_by_id(page, item.employee_id):
            self._add_employee(page, item)
            created = True
            if not self._open_employee_by_id(page, item.employee_id):
                raise PortalBusinessError(f"employee {item.employee_id} was added but not found")

        self._update_job(page, item)
        salary_artifact = self._ensure_salary_attachment(page, run_context, item)
        return WorkItemResult(
            item_key=item.item_key,
            status=OutcomeStatus.SUCCESS,
            reason="employee_up_to_date",
            details={
                "employee_id": item.employee_id,
                "full_name": item.full_name,
                "created": created,
                "job_title": item.job_title,
                "employment_status": item.employment_status,
                "salary_attachment": bool(salary_artifact),
            },
            artifact_path=salary_artifact,
        )

    def _login(self, page: Page) -> None:
        page.goto(self.config.orange_base_url, wait_until="domcontentloaded")
        page.locator("input[name='username']").fill(self.config.orange_username or "")
        page.locator("input[name='password']").fill(self.config.orange_password or "")
        page.locator("button[type='submit']").click()
        page.get_by_role("heading", name=re.compile("Dashboard", re.I)).wait_for()

    def _open_employee_by_id(self, page: Page, employee_id: str) -> bool:
        page.goto(f"{self.config.orange_base_url}/web/index.php/pim/viewEmployeeList")
        page.wait_for_load_state("networkidle")
        self._input_by_label(page, "Employee Id").fill(employee_id)
        page.get_by_role("button", name=re.compile("^Search$", re.I)).click()
        page.wait_for_load_state("networkidle")
        page.locator(".oxd-table-body").wait_for(state="attached")
        rows = page.locator(".oxd-table-card")
        for index in range(rows.count()):
            row = rows.nth(index)
            if employee_id in row.inner_text():
                row.locator("button:has(i.bi-pencil-fill)").click()
                page.wait_for_url(re.compile(r"/pim/viewPersonalDetails/empNumber/\d+"))
                return True
        return False

    def _add_employee(self, page: Page, item: EmployeeInput) -> None:
        page.goto(f"{self.config.orange_base_url}/web/index.php/pim/addEmployee")
        page.wait_for_load_state("networkidle")
        page.locator("input[name='firstName']").fill(item.first_name)
        if item.middle_name:
            page.locator("input[name='middleName']").fill(item.middle_name)
        page.locator("input[name='lastName']").fill(item.last_name)
        employee_id = self._input_by_label(page, "Employee Id")
        employee_id.fill("")
        employee_id.fill(item.employee_id)
        page.get_by_role("button", name=re.compile("^Save$", re.I)).click()
        page.wait_for_url(re.compile(r"/pim/viewPersonalDetails/empNumber/\d+"))

    def _update_job(self, page: Page, item: EmployeeInput) -> None:
        page.get_by_role("link", name=re.compile("^Job$", re.I)).click()
        self._select_dropdown(page, "Job Title", item.job_title)
        self._select_dropdown(page, "Employment Status", item.employment_status)
        page.get_by_role("button", name=re.compile("^Save$", re.I)).last.click()
        page.locator(".oxd-toast").wait_for()

    def _ensure_salary_attachment(
        self, page: Page, run_context: RunContext, item: EmployeeInput
    ):
        page.get_by_role("link", name=re.compile("^Salary$", re.I)).click()
        attachment_name = f"{item.employee_id}_salary_details.txt"
        if page.get_by_text(attachment_name).count():
            return None

        content = "\n".join(
            [
                f"Employee: {item.full_name}",
                f"Employee ID: {item.employee_id}",
                f"Job Title: {item.job_title}",
                f"Employment Status: {item.employment_status}",
                f"Salary: {item.salary_amount} {item.salary_currency}",
            ]
        )
        artifact_path = self.artifacts.write_text(
            business_date=run_context.business_date,
            portal=self.portal_name,
            item_key=item.employee_id,
            suffix="salary_details.txt",
            content=content,
        )

        page.get_by_role("button", name=re.compile("Add", re.I)).last.click()
        page.locator("input[type='file']").set_input_files(str(artifact_path))
        self._textarea_by_label(page, "Comment").fill(attachment_name)
        page.get_by_role("button", name=re.compile("^Save$", re.I)).last.click()
        page.locator(".oxd-toast").wait_for()
        return artifact_path

    def _input_by_label(self, page: Page, label: str) -> Locator:
        return page.locator(
            f"//label[normalize-space()='{label}']"
            "/ancestor::div[contains(@class, 'oxd-input-group')]//input"
        ).first

    def _textarea_by_label(self, page: Page, label: str) -> Locator:
        return page.locator(
            f"//label[normalize-space()='{label}']"
            "/ancestor::div[contains(@class, 'oxd-input-group')]//textarea"
        ).first

    def _select_dropdown(self, page: Page, label: str, option: str) -> None:
        dropdown = page.locator(
            f"//label[normalize-space()='{label}']"
            "/ancestor::div[contains(@class, 'oxd-input-group')]"
            "//div[contains(@class, 'oxd-select-text')]"
        ).first
        dropdown.click()
        page.get_by_role("option", name=re.compile(f"^{re.escape(option)}$", re.I)).click()
