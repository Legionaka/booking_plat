"""Owner and staff workspace browser coverage."""

from __future__ import annotations

import os
import re
import time

from playwright.sync_api import Browser, Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")


def sign_in_owner(page: Page) -> int:
    page.goto(f"{BASE_URL}/auth/login")
    page.locator("#login-email").fill(os.getenv("DEMO_OWNER_EMAIL", "owner@fade-lab.demo"))
    page.locator("#login-password").fill(
        os.getenv("DEMO_OWNER_PASSWORD", "DemoOnly-ChangeMe-2026!")
    )
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/account$"))
    memberships = page.evaluate(
        """async () => (await (await fetch('/api/auth/me')).json()).data.user.memberships"""
    )
    return next(item["business_id"] for item in memberships if item["role"] == "owner")


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
        route.fulfill(response)

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
    expect(page.get_by_text("only available to business owners")).to_be_visible()


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
