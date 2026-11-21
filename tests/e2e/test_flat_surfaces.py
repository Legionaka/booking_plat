"""Verify that every implemented server-rendered page has flat backgrounds."""

import os

import pytest
from playwright.sync_api import Browser

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")
PAGE_ROUTES = (
    "/auth/login",
    "/auth/register",
    "/auth/verify",
    "/auth/forgot",
    "/auth/forgot/sent",
    "/auth/reset?token=flat-style-check",
    "/account",
    "/account/bookings",
    "/account/bookings/1",
    "/app",
    "/b/fade-lab",
    "/b/fade-lab/book",
    "/b/fade-lab/book/time",
    "/b/fade-lab/book/review",
    "/account/bookings/1/reschedule",
    "/account/bookings/1/cancel",
    "/payments/return?booking_id=1",
    "/payments/cancel?booking_id=1",
    "/dev/components",
)


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_page_has_no_computed_gradient_background(browser: Browser, path: str):
    page = browser.new_page()
    response = page.goto(f"{BASE_URL}{path}")
    assert response is not None and response.status == 200
    backgrounds = page.locator("*").evaluate_all(
        "elements => elements.map(element => ({tag: element.tagName, "
        "className: typeof element.className === 'string' ? element.className : '', "
        "background: getComputedStyle(element).backgroundImage})) "
        ".filter(item => item.background.includes('gradient'))"
    )
    assert not backgrounds, f"Gradient backgrounds found on {path}: {backgrounds}"
    page.close()
