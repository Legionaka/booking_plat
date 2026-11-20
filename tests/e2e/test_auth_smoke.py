"""Real-browser authentication smoke and responsive screenshot coverage."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import Browser, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")
AUTH_PAGES = (
    ("login", "/auth/login"),
    ("register", "/auth/register"),
    ("verify", "/auth/verify"),
    ("forgot", "/auth/forgot"),
    ("forgot-sent", "/auth/forgot/sent"),
    ("reset", "/auth/reset"),
)


def verification_link_from_captured_output(log_path: Path) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        output = log_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Verify your email address: (http://[^\s]+)", output)
        if match:
            return match.group(1)
        time.sleep(0.1)
    raise AssertionError("No verification URL appeared in the captured console email output.")


def test_register_sign_in_link_and_login_submit_diagnostics(browser: Browser):
    page = browser.new_page()
    console_errors: list[str] = []
    csp_violations: list[dict[str, str]] = []
    failed_requests: list[dict[str, str]] = []
    page.add_init_script(
        "window.__cspViolations = [];"
        "document.addEventListener('securitypolicyviolation', (event) => "
        "window.__cspViolations.push({directive: event.violatedDirective, "
        "blockedURI: event.blockedURI}));"
    )
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            {"url": request.url, "failure": request.failure or "unknown"}
        ),
    )

    page.goto(f"{BASE_URL}/auth/register")
    page.get_by_role("link", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/auth/login$"))

    email = f"signin-probe-{uuid4().hex}@example.test"
    password = "SignInProbePassword-123!"
    page.goto(f"{BASE_URL}/auth/register")
    page.locator("#register-name").fill("Sign In Probe")
    page.locator("#register-email").fill(email)
    page.locator("#register-password").fill(password)
    page.get_by_role("button", name="Create account").click()
    expect(page).to_have_url(re.compile(r"/auth/verify$"))
    page.goto(verification_link_from_captured_output(Path(os.environ["E2E_EMAIL_LOG"])))
    expect(page.get_by_role("heading", name="Email verified")).to_be_visible()
    assert "token=" not in page.url

    page.goto(f"{BASE_URL}/auth/login")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    with page.expect_response(
        lambda response: response.url.endswith("/api/auth/login")
    ) as login_response:
        page.get_by_role("button", name="Sign in").click()
    assert login_response.value.status == 200
    expect(page).to_have_url(re.compile(r"/account$"))

    csp_violations.extend(
        page.evaluate("window.__cspViolations")
    )
    diagnostics = {
        "consoleErrors": console_errors,
        "cspViolations": csp_violations,
        "failedRequests": failed_requests,
        "loginStatus": login_response.value.status,
        "finalUrl": page.url,
    }
    output = Path(".artifacts/e2e/sign-in-diagnostics.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    assert not console_errors, diagnostics
    assert not csp_violations, diagnostics
    unexpected_failures = [
        item for item in failed_requests if item["failure"] != "net::ERR_ABORTED"
    ]
    diagnostics["expectedNavigationAborts"] = [
        item for item in failed_requests if item["failure"] == "net::ERR_ABORTED"
    ]
    output.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    assert not unexpected_failures, diagnostics


def test_password_caps_lock_listener_ignores_non_keyboard_events(browser: Browser):
    page = browser.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(f"{BASE_URL}/auth/register")
    page.locator("#register-password").evaluate(
        "input => input.dispatchEvent(new Event('keyup'))"
    )
    assert not page_errors, page_errors


def test_register_verify_login_sign_out_and_security(browser: Browser):
    page = browser.new_page()
    console_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )

    email = f"browser-{uuid4().hex}@example.test"
    password = "BrowserSmokePassword-123!"
    page.goto(f"{BASE_URL}/auth/register")
    page.locator("#register-name").fill("Browser Smoke User")
    page.locator("#register-email").fill(email)
    page.locator("#register-password").fill(password)
    page.get_by_role("button", name="Create account").click()
    expect(page).to_have_url(re.compile(r"/auth/verify$"))

    log_path = Path(os.environ["E2E_EMAIL_LOG"])
    verification_url = verification_link_from_captured_output(log_path)
    page.goto(verification_url)
    expect(page.get_by_role("heading", name="Email verified")).to_be_visible()
    assert urlsplit(page.url).path == "/auth/verify"
    assert "token=" not in page.url

    page.goto(f"{BASE_URL}/auth/login")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill("incorrect-password-123")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Email or password is incorrect.")).to_be_visible()

    page.goto(f"{BASE_URL}/auth/login?next=https://example.com")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/account$"))
    assert urlsplit(page.url).netloc == urlsplit(BASE_URL).netloc
    page.get_by_role("button", name="Sign out").click()

    # Encoded backslash variant of https\://example.com must stay on this origin.
    page.goto(f"{BASE_URL}/auth/login?next=https%5C%3A%2F%2Fexample.com")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/account$"))
    assert urlsplit(page.url).netloc == urlsplit(BASE_URL).netloc
    expect(page.get_by_text("Browser Smoke User")).to_be_visible()

    page.get_by_role("button", name="Sign out").click()
    expect(page).to_have_url(re.compile(r"/auth/login$"))
    csp_errors = [
        message
        for message in console_errors
        if "content security policy" in message.lower()
        or "violates the following content security policy" in message.lower()
    ]
    assert not csp_errors, "Browser console reported CSP errors: " + " | ".join(csp_errors)
    page.context.close()
