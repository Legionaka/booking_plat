"""Browser coverage for customer booking flows against the seeded demo business."""

from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import Browser, Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5001")


def sign_in(page: Page, customer: int = 1) -> None:
    page.goto(f"{BASE_URL}/auth/login")
    page.locator("#login-email").fill(f"customer{customer:02d}@fade-lab.demo")
    page.locator("#login-password").fill(f"Demo-Customer-{customer:02d}-ChangeMe!")
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/account$"))


def choose_available_time(page: Page, service_name: str) -> None:
    page.goto(f"{BASE_URL}/b/fade-lab/book")
    page.get_by_role("button", name=re.compile(service_name, re.IGNORECASE)).click()
    page.get_by_role("button", name="Choose a time").click()
    available_day = page.locator("[data-availability-strip] button:not([disabled])").first
    expect(available_day).to_be_visible()
    available_day.click()
    slot = page.locator("[data-slot-list] .slot-key").first
    expect(slot).to_be_visible()
    slot.click()
    page.get_by_role("link", name="Continue").click()
    expect(page.get_by_role("heading", name="Review your booking")).to_be_visible()


def test_customer_can_book_without_a_deposit(browser: Browser):
    page = browser.new_page()
    sign_in(page)
    choose_available_time(page, "Fade")
    page.get_by_role("button", name="Confirm booking").click()
    expect(page).to_have_url(re.compile(r"/book/confirmed/\d+$"))
    expect(page.get_by_role("heading", name="Your booking is confirmed.")).to_be_visible()


def test_deposit_booking_uses_scoped_payfast_handoff(browser: Browser):
    page = browser.new_page()
    handoff_requests: list[str] = []

    def intercept_payfast(route):
        handoff_requests.append(route.request.url)
        route.fulfill(status=200, content_type="text/html", body="<h1>PayFast simulator</h1>")

    page.route("https://sandbox.payfast.co.za/eng/process", intercept_payfast)
    sign_in(page)
    choose_available_time(page, "Fade and beard")
    expect(page.get_by_text(re.compile("Deposit due now"))).to_be_visible()
    page.get_by_role("button", name="Confirm booking").click()
    expect(page.get_by_role("heading", name="PayFast simulator")).to_be_visible(timeout=15000)
    assert handoff_requests == ["https://sandbox.payfast.co.za/eng/process"]


def test_two_customer_contexts_racing_for_one_slot_do_not_both_book(browser: Browser):
    context_a = browser.new_context()
    context_b = browser.new_context()
    page_a, page_b = context_a.new_page(), context_b.new_page()
    try:
        sign_in(page_a, 1)
        sign_in(page_b, 2)
        page_a.goto(f"{BASE_URL}/b/fade-lab")
        service = page_a.evaluate("""async () => {
          const r = await fetch('/api/b/fade-lab/services');
          return (await r.json()).data.find((item) => item.name === 'Fade');
        }""")
        dates = page_a.evaluate(
            """async (serviceId) => {
          const options = {
            timeZone:'Africa/Johannesburg',year:'numeric',month:'2-digit',day:'2-digit'
          };
          const parts = new Intl.DateTimeFormat('en-CA', options).formatToParts(new Date());
          const from = [
            parts.find(x=>x.type==='year').value,
            parts.find(x=>x.type==='month').value,
            parts.find(x=>x.type==='day').value
          ].join('-');
          const toDate = new Date(`${from}T12:00:00Z`); toDate.setUTCDate(toDate.getUTCDate()+6);
          const to = toDate.toISOString().slice(0,10);
          const query = new URLSearchParams({service:serviceId,staff:'any',from,to});
          const r = await fetch(`/api/b/fade-lab/availability?${query}`);
          return (await r.json()).data.days.find((day) => day.open)?.date;
        }""",
            service["id"],
        )
        assert dates, "The seeded business should have an open date within the next week."
        slots = page_a.evaluate(
            """async ({serviceId, date}) => {
          const query = new URLSearchParams({service:serviceId,staff:'any',date});
          const r = await fetch(`/api/b/fade-lab/slots?${query}`);
          return (await r.json()).data.slots;
        }""",
            {"serviceId": service["id"], "date": dates},
        )
        assert slots, "The selected open date should contain at least one slot."
        slot = slots[0]
        payload = {
            "service_id": service["id"],
            "staff_id": slot["staff_ids"][0],
            "start_at": slot["start_at"],
        }
        for page, label in ((page_a, "a"), (page_b, "b")):
            page.evaluate(
                """async ({payload, label}) => {
              const csrf = await fetch('/api/auth/csrf').then((r) => r.json());
              window[`race${label}`] = fetch('/api/b/fade-lab/bookings', {
                method:'POST', credentials:'same-origin',
                headers:{'Content-Type':'application/json','X-CSRF-Token':csrf.data.csrf_token},
                body:JSON.stringify(payload)
              }).then(async (response) => ({status:response.status, body:await response.json()}));
            }""",
                {"payload": payload, "label": label},
            )
        result_a = page_a.evaluate("window.racea")
        result_b = page_b.evaluate("window.raceb")
        assert result_a["status"] in {201, 409, 422}
        assert result_b["status"] in {201, 409, 422}
        assert 201 in {result_a["status"], result_b["status"]}
        assert not (result_a["status"] in {200, 201} and result_b["status"] in {200, 201})
    finally:
        context_a.close()
        context_b.close()


def test_late_cancellation_displays_contact_business_state(browser: Browser):
    page = browser.new_page()
    sign_in(page)
    page.goto(f"{BASE_URL}/account/bookings")
    expect(page.get_by_role("heading", name="My bookings")).to_be_visible()
    booking_links = page.locator("[data-booking-list] a")
    expect(booking_links.first).to_be_visible()
    booking_id = booking_links.first.get_attribute("href").rstrip("/").split("/")[-1]
    page.goto(f"{BASE_URL}/account/bookings/{booking_id}/cancel")
    page.route(
        re.compile(r".*/api/bookings/\d+$"),
        lambda route: route.fulfill(
            status=403,
            content_type="application/json",
            body=(
                '{"error":{"code":"late_cancellation",'
                '"message":"This booking starts in under 24 hours, '
                'so it cannot be cancelled online."}}'
            ),
        ),
    )
    page.get_by_role("button", name="Cancel appointment").click()
    expect(page.get_by_text("This booking starts in under 24 hours")).to_be_visible()


def test_customer_can_cancel_before_cutoff(browser: Browser):
    page = browser.new_page()
    sign_in(page)
    booking_id = page.evaluate("""async () => {
      const bookings = (await fetch('/api/me/bookings?filter=upcoming').then((r)=>r.json())).data;
      const cutoff = Date.now() + 25 * 60 * 60 * 1000;
      return bookings.find((item) =>
        ['confirmed','pending'].includes(item.status) &&
        Date.parse(item.start_at) > cutoff
      )?.id;
    }""")
    if not booking_id:
        pytest.skip("The seeded customer has no active booking more than 25 hours ahead.")
    page.goto(f"{BASE_URL}/account/bookings/{booking_id}/cancel")
    page.get_by_role("button", name="Cancel appointment").click()
    expect(page).to_have_url(re.compile(rf"/account/bookings/{booking_id}/cancelled$"))
    expect(page.get_by_role("heading", name="Your booking has been cancelled.")).to_be_visible()


def test_customer_can_reschedule_to_an_available_slot(browser: Browser):
    page = browser.new_page()
    sign_in(page)
    booking = page.evaluate("""async () => {
      const rows = (await fetch('/api/me/bookings?filter=upcoming').then((r)=>r.json())).data;
      return rows.find((item) => ['confirmed','pending'].includes(item.status));
    }""")
    if not booking:
        pytest.skip("The seeded customer has no active upcoming booking to reschedule.")
    dates = page.evaluate(
        """async (booking) => {
      const business = (await fetch(`/api/b/fade-lab`).then((r)=>r.json())).data;
      const options = {timeZone:business.timezone,year:'numeric',month:'2-digit',day:'2-digit'};
      const parts = new Intl.DateTimeFormat('en-CA', options).formatToParts(new Date());
      const from = [
        parts.find(x=>x.type==='year').value,
        parts.find(x=>x.type==='month').value,
        parts.find(x=>x.type==='day').value
      ].join('-');
      const endDate = new Date(`${from}T12:00:00Z`); endDate.setUTCDate(endDate.getUTCDate()+14);
      const to = endDate.toISOString().slice(0,10);
      const rangeQuery = new URLSearchParams({
        service:booking.service_id,staff:booking.staff_id,from,to
      });
      const range = await fetch(`/api/b/fade-lab/availability?${rangeQuery}`).then((r)=>r.json());
      for (const day of range.data.days.filter((item)=>item.open)) {
        const slotQuery = new URLSearchParams({
          service:booking.service_id,staff:booking.staff_id,date:day.date
        });
        const response = await fetch(`/api/b/fade-lab/slots?${slotQuery}`).then((r)=>r.json());
        const slot = response.data.slots.find((item)=>item.start_at !== booking.start_at);
        if (slot) return {date:day.date,slot};
      }
      return null;
    }""",
        booking,
    )
    if not dates:
        pytest.skip("The seeded service has no alternate open slot in the next two weeks.")
    page.goto(f"{BASE_URL}/account/bookings/{booking['id']}/reschedule")
    page.locator("[data-reschedule-date]").fill(dates["date"])
    slot = page.locator("[data-reschedule-slots] .slot-key").first
    expect(slot).to_be_visible()
    slot.click()
    page.get_by_role("button", name="Confirm new time").click()
    expect(page).to_have_url(re.compile(rf"/account/bookings/{booking['id']}/rescheduled$"))
    expect(page.get_by_role("heading", name="Your booking has been rescheduled.")).to_be_visible()


def test_payment_return_waits_for_backend_confirmation(browser: Browser):
    page = browser.new_page()
    sign_in(page)
    page.goto(f"{BASE_URL}/account/bookings")
    bookings = page.evaluate(
        """async () => (await fetch('/api/me/bookings?filter=upcoming')).json().data"""
    )
    pending = next((item for item in bookings if item["status"] == "pending"), None)
    if pending is None:
        pytest.skip("The deterministic demo seed has no pending deposit booking for this run.")
    page.goto(f"{BASE_URL}/payments/return?booking_id={pending['id']}")
    expect(page.get_by_role("heading", name="Waiting for payment confirmation")).to_be_visible()
    expect(page.get_by_text(re.compile("page will not confirm a booking"))).to_be_visible()
