"""Accessibility and keyboard-interaction checks for the live component sheet."""

from __future__ import annotations

import os

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")


def test_component_sheet_has_no_serious_or_critical_axe_violations(browser: Browser):
    page = browser.new_page()
    page.goto(f"{BASE_URL}/dev/components")
    results = Axe().run(page)
    serious = [
        violation
        for violation in results.response["violations"]
        if violation["impact"] in {"serious", "critical"}
    ]
    assert not serious, results.generate_report()


def test_dialog_traps_focus_and_escape_closes(browser: Browser):
    page = browser.new_page()
    page.goto(f"{BASE_URL}/dev/components")
    page.get_by_role("button", name="Open modal").click()
    dialog = page.get_by_role("dialog", name="Cancel booking?")
    expect(dialog).to_be_visible()
    page.keyboard.press("Shift+Tab")
    expect(page.get_by_role("button", name="Confirm")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Close dialog")).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()


def test_tabs_update_selection_and_panel(browser: Browser):
    page = browser.new_page()
    page.goto(f"{BASE_URL}/dev/components")
    page.get_by_role("tab", name="Past").click()
    expect(page.get_by_role("tabpanel", name="Past")).to_be_visible()
    expect(page.get_by_role("tab", name="Past")).to_have_attribute("aria-selected", "true")
