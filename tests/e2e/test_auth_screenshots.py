"""Responsive full-page screenshots for all implemented auth pages."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")
AUTH_PAGES = (
    ("login", "/auth/login"),
    ("register", "/auth/register"),
    ("verify", "/auth/verify"),
    ("forgot", "/auth/forgot"),
    ("forgot-sent", "/auth/forgot/sent"),
    ("reset", "/auth/reset"),
)


@pytest.mark.parametrize("page_name,path", AUTH_PAGES)
@pytest.mark.parametrize("width", (1440, 820, 390))
@pytest.mark.parametrize("reduced_motion", ("reduce", "no-preference"))
def test_auth_page_full_page_screenshots(
    browser: Browser, page_name: str, path: str, width: int, reduced_motion: str
):
    context = browser.new_context(
        viewport={"width": width, "height": 1000}, reduced_motion=reduced_motion
    )
    page = context.new_page()
    response = page.goto(f"{BASE_URL}{path}")
    assert response is not None and response.status == 200
    filename = f"{page_name}-{width}-{reduced_motion}.png"
    screenshot_path = Path(".artifacts/e2e/screenshots") / filename
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_path), full_page=True)
    context.close()
