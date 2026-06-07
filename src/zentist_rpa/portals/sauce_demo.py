from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from playwright.sync_api import Page, sync_playwright

from zentist_rpa.exceptions import PortalBusinessError
from zentist_rpa.models import (
    OutcomeStatus,
    RunContext,
    SauceAccountInput,
    WorkItemResult,
)
from zentist_rpa.portals.base import BasePortalRunnerZX

SAUCE_ACCOUNTS = [
    "standard_user",
    "locked_out_user",
    "problem_user",
    "performance_glitch_user",
    "error_user",
    "visual_user",
]


class SauceDemoRunner(BasePortalRunnerZX[SauceAccountInput, Page]):
    portal_name = "sauce_demo"

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

    def item_key(self, item: SauceAccountInput) -> str:
        return item.item_key

    def process_item(
        self, session: Page, run_context: RunContext, item: SauceAccountInput
    ) -> WorkItemResult:
        page = session
        self._login(page, item)
        selected_items = self._add_items_to_cart(page, item.item_count)
        order_details = self._checkout(page, item, selected_items)
        artifact_path = self.artifacts.write_json(
            business_date=run_context.business_date,
            portal=self.portal_name,
            item_key=item.item_key,
            suffix="order.json",
            payload=order_details,
        )
        self._finish_order(page)
        return WorkItemResult(
            item_key=item.item_key,
            status=OutcomeStatus.SUCCESS,
            reason="order_completed",
            details={
                "confirmation": order_details.get("confirmation"),
                "item_count": len(selected_items),
                "total": order_details.get("total"),
            },
            artifact_path=artifact_path,
        )

    def _login(self, page: Page, item: SauceAccountInput) -> None:
        page.context.clear_cookies()
        page.goto(self.config.sauce_base_url, wait_until="domcontentloaded")
        page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
        page.goto(self.config.sauce_base_url, wait_until="domcontentloaded")
        page.locator("#user-name").fill(item.username)
        page.locator("#password").fill(item.password)
        page.locator("#login-button").click()
        error = page.locator("[data-test='error']")
        if error.count() and error.is_visible():
            raise PortalBusinessError(error.inner_text().strip())
        page.locator(".inventory_list").wait_for()

    def _add_items_to_cart(self, page: Page, count: int) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        cards = page.locator(".inventory_item")
        if cards.count() < count:
            raise PortalBusinessError(f"expected at least {count} inventory items")
        for index in range(count):
            card = cards.nth(index)
            name = card.locator(".inventory_item_name").inner_text().strip()
            price = card.locator(".inventory_item_price").inner_text().strip()
            card.locator("button").click()
            selected.append({"name": name, "price": price})
        cart_badge = page.locator(".shopping_cart_badge")
        if not cart_badge.count() or cart_badge.inner_text().strip() != str(count):
            raise PortalBusinessError("cart did not contain the expected number of items")
        return selected

    def _checkout(
        self, page: Page, item: SauceAccountInput, selected_items: list[dict[str, str]]
    ) -> dict[str, Any]:
        page.locator(".shopping_cart_link").click()
        page.locator("[data-test='checkout']").click()
        page.locator("[data-test='firstName']").fill(item.first_name)
        page.locator("[data-test='lastName']").fill(item.last_name)
        page.locator("[data-test='postalCode']").fill(item.postal_code)
        page.locator("[data-test='continue']").click()

        checkout_items = [
            row.inner_text().strip()
            for row in page.locator(".cart_item .inventory_item_name").all()
        ]
        if len(checkout_items) != len(selected_items):
            raise PortalBusinessError("checkout overview item count mismatch")

        total = page.locator(".summary_total_label").inner_text().strip()
        tax = page.locator(".summary_tax_label").inner_text().strip()
        page.locator("[data-test='finish']").click()
        confirmation = page.locator(".complete-header").inner_text().strip()
        if not confirmation:
            raise PortalBusinessError("missing order confirmation")

        return {
            "account": item.username,
            "items": selected_items,
            "checkout_items": checkout_items,
            "tax": tax,
            "total": total,
            "confirmation": confirmation,
            "confirmation_url": page.url,
        }

    def _finish_order(self, page: Page) -> None:
        back_home = page.locator("[data-test='back-to-products']")
        if back_home.count():
            back_home.click()
