"""Owner and staff workspace browser coverage."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import Browser, Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")


def sign_in_owner(page: Page) -> int:
    email = os.getenv("DEMO_OWNER_EMAIL", "owner@fade-lab.demo")
    password = os.getenv("DEMO_OWNER_PASSWORD", "DemoOnly-ChangeMe-2026!")
    page.goto(f"{BASE_URL}/auth/login", wait_until="domcontentloaded")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    with page.expect_response("**/api/auth/login") as response_info:
        page.get_by_role("button", name="Sign in").click()
    response = response_info.value
    if response.status != 200:
        payload = json.loads(response.request.post_data or "{}")
        raise AssertionError(
            f"Login API returned {response.status}; "
            f"submitted email matches={payload.get('email') == email}, "
            f"password matches={payload.get('password') == password}; "
            f"error={response.json().get('error', {}).get('code')}"
        )
    expect(page).to_have_url(re.compile(r"/app/\d+/dashboard$"))
    memberships = page.evaluate(
        """async () => (await (await fetch('/api/auth/me')).json()).data.user.memberships"""
    )
    return next(item["business_id"] for item in memberships if item["role"] == "owner")


def test_owner_dashboard_and_analytics_screenshots(browser: Browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    business_id = sign_in_owner(page)
    screenshot_dir = Path(__file__).resolve().parents[2] / "docs" / "assets" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.goto(f"{BASE_URL}/app/{business_id}/dashboard")
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()
    page.screenshot(path=screenshot_dir / "owner-dashboard.png", full_page=True)
    page.goto(f"{BASE_URL}/app/{business_id}/analytics")
    expect(page.get_by_role("heading", name="Analytics")).to_be_visible()
    page.screenshot(path=screenshot_dir / "analytics.png", full_page=True)


def test_owner_onboarding_creates_business_service_staff_and_hours(browser: Browser):
    page = browser.new_page()
    sign_in_owner(page)
    created_business_id = 0

    def me(route):
        memberships = (
            [{"business_id": created_business_id, "role": "owner"}]
            if created_business_id
            else []
        )
        route.fulfill(json={"data": {"user": {"memberships": memberships}}})

    def create_business(route):
        nonlocal created_business_id
        response = route.fetch()
        created_business_id = response.json()["data"]["id"]
        route.fulfill(response=response)

    page.route("**/api/auth/me", me)
    page.route("**/api/admin/businesses", create_business)
    page.goto(f"{BASE_URL}/app/onboarding")
    page.get_by_label("Business name").fill("Browser setup shop")
    page.get_by_label("Booking page slug").fill(f"browser-setup-{int(time.time())}")
    page.get_by_role("button", name="Create business").click()
    page.get_by_label("Service name").fill("First session")
    page.get_by_label("Duration in minutes").fill("30")
    page.get_by_label("Price in ZAR").fill("25")
    page.get_by_role("button", name="Add service").click()
    page.get_by_label("Staff member name").fill("First staff member")
    page.get_by_role("button", name="Add staff and hours").click()
    expect(page.get_by_role("heading", name="Your booking page is ready")).to_be_visible()
    page.get_by_role("button", name="Open workspace").click()
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()


def test_owner_services_crud_calendar_and_status_drawer(browser: Browser):
    page = browser.new_page()
    business_id = sign_in_owner(page)
    page.goto(f"{BASE_URL}/app/{business_id}/services")
    page.get_by_role("button", name="Create service").click()
    page.get_by_label("Name", exact=True).fill("Browser service")
    page.get_by_label("Duration (minutes)").fill("35")
    page.get_by_label("Price (ZAR)").fill("45")
    page.get_by_role("button", name="Save service").click()
    expect(page.get_by_text("Browser service")).to_be_visible()
    page.get_by_role("link", name="Week view").click()
    expect(page.get_by_role("heading", name="Week view")).to_be_visible()
    page.goto(f"{BASE_URL}/app/{business_id}/bookings")
    expect(page.get_by_role("heading", name="Bookings")).to_be_visible()
    rows = page.locator("[data-booking-list] tbody tr")
    if rows.count() == 0 or "No records yet" in rows.first.inner_text():
        page.goto(f"{BASE_URL}/app/{business_id}/dashboard")
        expect(page.get_by_role("heading", name="Today’s timeline")).to_be_visible()
        return
    page.locator("[data-open-booking]").first.click()
    expect(
        page.get_by_role("dialog").get_by_role("heading", name=re.compile("Booking #"))
    ).to_be_visible()


def test_owner_calendar_booking_status_action(browser: Browser):
    page = browser.new_page()
    business_id = sign_in_owner(page)

    def calendar(route):
        day = route.request.url.split("date=")[-1]
        route.fulfill(
            json={
                "data": {
                    "date": day,
                    "timezone": "Africa/Johannesburg",
                    "staff": [
                        {
                            "id": 10,
                            "display_name": "Demo stylist",
                            "working_windows": [],
                            "time_off": [],
                            "bookings": [
                                {
                                    "id": 999,
                                    "start_at": f"{day}T08:00:00Z",
                                    "end_at": f"{day}T08:30:00Z",
                                    "local_start": f"{day}T10:00:00+02:00",
                                    "status": "pending",
                                    "service": "Cut",
                                    "customer_name": "Test customer",
                                    "deposit_status": "pending",
                                }
                            ],
                        }
                    ],
                }
            }
        )

    page.route(f"**/api/admin/businesses/{business_id}/calendar?date=*", calendar)
    page.route(
        f"**/api/admin/businesses/{business_id}/bookings?limit=100",
        lambda route: route.fulfill(
            json={
                "data": [
                    {
                        "id": 999,
                        "status": "pending",
                        "start_at": "2026-11-21T08:00:00Z",
                        "price_cents": 18000,
                        "deposit_cents": 5000,
                        "customer_id": 1,
                        "customer_name": "Test customer",
                        "service_id": 1,
                        "service_name": "Cut",
                        "staff_id": 10,
                        "staff_name": "Demo stylist",
                    }
                ]
            }
        ),
    )
    actions: list[dict] = []

    def confirm(route):
        actions.append(route.request.post_data_json)
        route.fulfill(json={"data": {"id": 999, "status": "confirmed"}})

    page.route("**/api/bookings/999", confirm)
    page.goto(f"{BASE_URL}/app/{business_id}/dashboard")
    page.get_by_role("button", name=re.compile("Test customer")).click()
    page.get_by_role("dialog").get_by_role("button", name="Confirm").click()
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()
    assert actions == [{"action": "confirm"}]


def test_staff_workspace_hides_owner_sections(browser: Browser):
    page = browser.new_page()
    business_id = sign_in_owner(page)
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            json={
                "data": {"user": {"memberships": [{"business_id": business_id, "role": "staff"}]}}
            }
        ),
    )
    page.goto(f"{BASE_URL}/app/{business_id}/dashboard")
    expect(page.get_by_role("heading", name="My calendar")).to_be_visible()
    expect(page.get_by_role("link", name="Services")).to_have_count(0)
    expect(page.locator("[data-create-booking]")).to_be_hidden()
    page.goto(f"{BASE_URL}/app/{business_id}/services")
    expect(
        page.get_by_text("This section is only available to business owners.", exact=True)
    ).to_be_visible()


def test_chart_modules_render_accessible_flat_svg(browser: Browser):
    page = browser.new_page()
    page.goto(f"{BASE_URL}/offline")
    for name in ("svg", "sparkline", "area", "donut", "heatmap", "ring"):
        page.add_script_tag(url=f"{BASE_URL}/static/js/charts/{name}.js")
    result = page.evaluate("""() => {
      const charts = window.BookingCharts;
      const values = [
        charts.sparkline([0, 2, 3], 'Visits'),
        charts.area([{value: 2}, {value: 4}], 'Revenue'),
        charts.donut([{value: 2}], 'Status'),
        charts.heatmap([{value: 3}], 'Activity'),
        charts.ring(42, 'Team')
      ];
      return values.map((svg) => ({
        tag: svg.tagName,
        role: svg.getAttribute('role'),
        label: svg.getAttribute('aria-label'),
        gradients: svg.querySelectorAll('linearGradient,radialGradient').length
      }));
    }""")
    assert len(result) == 5
    assert all(
        item["tag"] == "svg" and item["role"] == "img" and item["label"] and item["gradients"] == 0
        for item in result
    )
