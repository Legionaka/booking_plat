"""Figma-sized auth screenshots and rendered layout guardrails."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")
SCREENSHOTS = Path(os.getenv("AUTH_LAYOUT_SCREENSHOT_DIR", ".artifacts/e2e/auth-layout"))
SCREEN_SIZES = (
    ("1920x1080", 1920, 1080),
    ("2560x1440", 2560, 1440),
    ("1440x900", 1440, 900),
    ("820x1180", 820, 1180),
    ("390x844", 390, 844),
)
AUTH_PAGES = (
    ("login", "/auth/login"),
    ("register", "/auth/register"),
    ("verify", "/auth/verify"),
    ("forgot", "/auth/forgot"),
    ("forgot-sent", "/auth/forgot/sent"),
    ("reset", "/auth/reset"),
)


@pytest.mark.parametrize("page_name,path", AUTH_PAGES)
@pytest.mark.parametrize("width,height", ((1920, 1080), (390, 844)))
def test_auth_panel_and_primary_action_geometry(
    browser: Browser, page_name: str, path: str, width: int, height: int
):
    context = browser.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=1
    )
    page = context.new_page()
    if page_name == "reset":
        page.route(
            "**/api/auth/reset",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"error":{"code":"dependency_unavailable","message":"Retry."}}',
            ),
        )
        path = "/auth/reset?token=layout-probe"
    response = page.goto(f"{BASE_URL}{path}")
    assert response is not None and response.status == 200

    panel = page.locator(".auth-card")
    expect(panel).to_be_visible()
    panel_width = panel.bounding_box()["width"]
    assert 360 <= panel_width <= 520, f"{page_name} panel width was {panel_width}px at {width}px"

    if page_name == "forgot-sent":
        primary_action = panel.locator("a.button").first
    else:
        primary_action = panel.locator(".button--primary").first
    expect(primary_action).to_be_visible()
    expect(primary_action).to_be_enabled()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    context.close()


@pytest.mark.parametrize(
    "page_name,path", (("login", "/auth/login"), ("register", "/auth/register"))
)
@pytest.mark.parametrize("size_name,width,height", SCREEN_SIZES)
def test_login_and_register_layout_screenshots(
    browser: Browser, page_name: str, path: str, size_name: str, width: int, height: int
):
    context = browser.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=1
    )
    page = context.new_page()
    response = page.goto(f"{BASE_URL}{path}")
    assert response is not None and response.status == 200
    page.evaluate("document.fonts.ready")
    if width == 390:
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = SCREENSHOTS / f"{page_name}-{size_name}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output), full_page=True)
    context.close()
