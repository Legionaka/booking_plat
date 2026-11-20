# API outline

Base path: `/api`. JSON endpoints use `application/json`, except the PayFast ITN webhook, which accepts the provider's form payload. Authentication uses secure, HttpOnly session cookies. All tenant-owned reads and writes must be scoped to the active `business_id`; owner and staff endpoints require role checks.

This document records the planned API surface from `docs/planning.md`. Request and response fields below are illustrative where the plan does not define a complete schema; validate and finalize them with the endpoint implementation.

## Conventions

- Error response: `{ "error": { "code": "string", "message": "string" } }`.
- Use `400` for malformed or invalid input, `401` for missing authentication, `403` for insufficient role, `404` for resources outside the caller's scope or not found, `409` for state conflicts or a slot taken, and `429` for rate limits.
- Admin list endpoints use `limit` and `offset` (maximum limit 100).
- Store timestamps in UTC and serialize them as ISO 8601 timestamps with an offset, preferably `Z`. Interpret business-local dates using the business timezone.
- Store money as integer cents. Never accept a client-supplied price as authoritative; calculate it on the server and snapshot it on the booking.
- Rate-limit login, public availability reads, and booking creation.
- Validate all IDs, dates, state transitions, and role access server-side.

## Authentication

Authentication uses an opaque server-side Redis session. The browser cookie is HttpOnly, SameSite=Lax, and Secure when `SESSION_COOKIE_SECURE=true`. Register and login always require `X-CSRF-Token`; obtain it from `GET /api/auth/csrf` before posting. Other state-changing requests require the token when a session cookie is present.

| Method | Path | Purpose | Access / limit |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | Create an unverified account and send a 24-hour verification token | Public; 20/hour per IP (configurable) |
| POST | `/api/auth/verify` | Verify an email using a signed, single-use token | Public |
| POST | `/api/auth/resend-verification` | Send a fresh link only when an account exists and is unverified; return the same success for all valid emails | Public; 3/hour per IP and email, plus 30/hour per IP |
| POST | `/api/auth/login` | Verify credentials and rotate into an authenticated server-side session | Public; 5/minute per IP and email, plus 30/hour per IP |
| POST | `/api/auth/logout` | Delete the current server-side session | Authenticated; CSRF required when a session cookie is present |
| POST | `/api/auth/forgot` | Request a one-hour reset token; response does not reveal account existence | Public; 5/hour per email and 30/hour per IP |
| POST | `/api/auth/reset` | Set a new password with a signed, single-use token | Public; 5/hour per IP and token fingerprint, plus 30/hour per IP |
| GET | `/api/auth/me` | Return the current user and business memberships | Authenticated |
| GET | `/api/auth/csrf` | Create or return the CSRF token for the current session | Public |

Register accepts `{ "email", "password", "full_name" }`; passwords must contain 10 to 128 characters. Login accepts `{ "email", "password" }`. Verify accepts `{ "token" }`. Forgot accepts `{ "email" }`. Reset accepts `{ "token", "new_password" }`, with a length between 10 and 128 characters.

Invalid credentials always return `401` with `Email or password is incorrect.` Unverified accounts receive a distinct verification-required response. Forgot always returns the same success body whether the email exists. Verification tokens expire after 24 hours; reset tokens expire after one hour and stop working after the password hash changes. Request bodies are validated with Pydantic and reject unknown fields.

## Public business and booking

`GET /api/config` returns `{ "demo_mode": true|false }` without authentication. A frontend may use this flag to show that demo payments are not real.

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| GET | `/api/b/<slug>/services` | List active services for a business | Public |
| GET | `/api/b/<slug>` | Return public-safe business name, slug, and timezone | Public; rate limited |
| GET | `/api/b/<slug>/slots?service=<id>&staff=<id>&date=<YYYY-MM-DD>` | Return available UTC slot start times for the requested business-local date | Public |
| POST | `/api/b/<slug>/bookings` | Create a booking; respond `409` if the requested slot was taken | Customer session |

For availability reads, `staff=any` merges eligible staff. Slot generation considers working hours, service assignment, time off, active bookings, service duration and buffer, slot step, minimum notice, and maximum advance.

Booking creation should accept the chosen service, staff (if selected), and slot start time. The server resolves the business, confirms availability, calculates the price/deposit, and creates either a `pending` booking with a hold expiry when a deposit is required or a `confirmed` booking when no deposit is required. Exact request field names are TBD.

## Customer bookings

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| PATCH | `/api/bookings/<id>` | Cancel, reschedule, or request an allowed status change | Customer or authorized owner/staff |
| GET | `/api/me/bookings` | List the authenticated customer's booking history | Customer session |

Enforce the business cancellation cutoff for customer cancellations. Keep allowed state transitions in one service function. Supported transitions are:

| From | To | Trigger |
| --- | --- | --- |
| New | `pending` | Slot selected and deposit required |
| New | `confirmed` | Slot selected and no deposit required |
| `pending` | `confirmed` | Payment received or owner confirms |
| `pending` | `cancelled` | Hold expires or customer cancels |
| `confirmed` | `cancelled` | Customer or owner cancels, subject to customer cutoff |
| `confirmed` | `completed` | Staff marks service complete |
| `confirmed` | `no_show` | Staff marks no-show after start time |

Reject all other transitions with a clear conflict error. The plan's customer-facing late-cancellation message is: “This booking starts in under 24 hours, so it can't be cancelled online. Contact the business to change it.” The default cutoff is 24 hours and is configurable per business.

## Owner and staff management

Implemented owner and staff management routes, permissions, pagination, audit logging, and request details are documented in the Business administration section below. Booking calendar routes remain planned.

## Payments and health

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| POST | `/api/bookings/<id>/pay` | Start or reuse a pending PayFast payment; return its action URL and signed form fields | Booking owner |
| POST | `/payments/handoff/<id>` | Render the server-generated PayFast form and submit it using an external script | Booking owner; CSRF required |
| POST | `/api/payments/payfast/itn` | Validate PayFast ITN signature and amount, then apply payment idempotently | PayFast callback |
| GET | `/health` | Liveness check | Public or infrastructure-only (deployment decision TBD) |
| GET | `/ready` | Postgres and Redis readiness check; returns only a status | Infrastructure |

Payment handling must be idempotent using `(provider, provider_ref)`. Verify the signature and expected amount before confirming a booking. Repeated callbacks must not duplicate payment effects.

## Common response shapes

Successful resource response (illustrative):

```json
{
  "data": {
    "id": 123
  }
}
```

Paginated response (illustrative):

```json
{
  "data": [],
  "pagination": {
    "next_cursor": null
  }
}
```

Error response:

```json
{
  "error": {
    "code": "slot_unavailable",
    "message": "That time was just booked. Pick another slot."
  }
}
```
# Registration and CSRF disclosure

Registration intentionally returns `409 email_in_use` for a duplicate address so a person can correct a typo or proceed to sign in instead of being told only that a verification email was sent. This reveals whether an email has an account and carries an account-enumeration risk. Login and register always require a synchronizer CSRF token. Verify, forgot and reset require it only when the caller already has a session cookie; logout is session-authenticated and always needs the token.

Auth throttles are environment-configurable. Defaults: registration 20/hour/IP; login 5/minute/IP+email and 30/hour/IP; forgot 5/hour/IP+email and 30/hour/IP; reset 5/hour/IP+token and 30/hour/IP; resend verification 3/hour/IP+email and 30/hour/IP. Redis is required for sessions and rate limiting; auth endpoints return 503 when it is unavailable.

Verification and password reset emails link to `PUBLIC_BASE_URL/auth/verify?token=...` and `PUBLIC_BASE_URL/auth/reset?token=...`. Registration intentionally returns `409 email_in_use`; this account-enumeration trade-off is described above.

## Business administration (slice 3)

All administration endpoints are scoped under `/api/admin/businesses/{business_id}`. A verified signed-in user can create a business and becomes its owner. Owners manage business settings, services, staff, staff-service assignments, working hours, and time off. Staff can read services, staff and hours, and manage only their own time off. Membership-scoped resources belonging to another business return 404. List routes accept `limit` (1–100, default 50) and `offset` (default 0).

- `POST /api/admin/businesses`; `GET|PATCH /api/admin/businesses/{business_id}`
- `GET|POST /api/admin/businesses/{business_id}/services`; `PATCH /.../services/{service_id}`; `POST /.../services/{service_id}/deactivate`
- `GET|POST /api/admin/businesses/{business_id}/staff`; `PATCH /.../staff/{staff_id}`; `POST /.../staff/{staff_id}/deactivate`
- `POST|DELETE /.../staff/{staff_id}/services/{service_id}` assigns or unassigns a service

Service and staff deactivation is soft; it preserves existing booking references and remains allowed when future bookings exist. The response includes `affected_future_bookings`, counting future pending and confirmed bookings for the deactivated resource.

- `GET|PUT /.../staff/{staff_id}/working-hours` replaces the whole weekly schedule on PUT
- `GET|POST /.../staff/{staff_id}/time-off`; `DELETE /.../staff/{staff_id}/time-off/{time_off_id}`
- Public active-only catalog reads: `GET /api/b/{slug}/services` and `/staff`.

## Availability (slice 4)

Availability reads are public, rate limited to 60 requests per minute per IP by default, and return only active services/staff who offer that service. `AVAILABILITY_MINIMUM_NOTICE_MINUTES` defaults to 120; `AVAILABILITY_MAXIMUM_ADVANCE_DAYS` defaults to 60. The date range endpoint accepts at most 62 inclusive days and loads schedule and occupancy rows for the range in a fixed query count.

- `GET /api/b/{slug}/slots?service={id}&staff={id|any}&date=YYYY-MM-DD`
- `GET /api/b/{slug}/availability?service={id}&staff={id|any}&from=YYYY-MM-DD&to=YYYY-MM-DD`

The slots response contains the business `timezone` and `slots` with UTC `start_at` and `end_at`, business-local `local_start`, and the eligible `staff_ids`. With `staff=any`, equal start times are merged across eligible staff. Availability returns `timezone` and per-day `open_slots` counts plus an `open` boolean. Past dates yield no slots. Unknown businesses, services, or staff return 404; malformed dates and selecting staff who do not offer the service return 422. Confirmed bookings and unexpired pending holds block through `blocked_until`; expired pending holds do not.


## Booking creation and lifecycle (slice 5)

`POST /api/b/{slug}/bookings` requires a verified customer session and CSRF token. The body contains `service_id`, `staff_id` (an ID or `any`) and an offset-aware UTC `start_at`. The server revalidates the selected slot against availability, snapshots service price/deposit, and creates a confirmed booking when no deposit is due or a pending hold otherwise. Exact same-customer retries return the existing active booking with 200. A raced slot conflict returns 409 `slot_taken`; unavailable or invalid starts return 422 `not_available`.

`HOLD_MINUTES` defaults to 15, `MAX_PENDING_HOLDS_PER_USER` defaults to 3 and `BOOKING_CREATE_RATE_LIMIT` defaults to 10 per minute.

- `PATCH /api/bookings/{id}` accepts `action`: `cancel`, `reschedule` (with `start_at` and optional `staff_id`), `confirm`, `complete`, or `no_show`. Customer cancellation and rescheduling obey the business cutoff; business owners and the assigned staff can manage the booking.
- `GET /api/me/bookings` lists the customer's bookings and accepts `filter=upcoming|past`, `limit` and `offset`; `GET /api/me/bookings/{id}` reads one owned booking.
- `GET /api/admin/businesses/{id}/bookings` lists business bookings with optional `from`, `to`, `staff`, `status`, `limit` and `offset`. Owners see all business bookings; staff see only rows for their linked staff record.
- `flask bookings expire-holds` cancels expired pending holds. Each create and state transition adds an audit row.

Confirmed bookings write confirmation and due reminder notifications to the transactional outbox in the booking transaction. Pending bookings are not notified until confirmed. Delivery is handled by the RQ worker; see [jobs.md](jobs.md) for worker and scheduler commands, retry behavior, and notification contents.

## PayFast deposits (slice 7)

- `POST /api/bookings/{id}/pay` requires the booking owner's logged-in session and CSRF token. It reuses a pending PayFast payment for that booking, extends the pending hold by at least `PAYMENT_HOLD_MINUTES`, and returns the PayFast action URL plus signed form fields.
- `POST /api/payments/payfast/itn` accepts PayFast's public form-encoded callback. It verifies the ordered signature, source IP, merchant, payment reference, amount, and PayFast server validation before changing payment or booking state. Only ITN confirmation confirms a booking; the browser return URL never does.
- `GET /api/me/bookings/{id}` includes `payment_status` for the latest PayFast payment, or `null` when payment has not started.
- `GET /api/admin/businesses/{id}/payments` is owner-only and supports `status`, `from`, `to`, `limit`, and `offset` filters.

See [payments.md](payments.md) for signature details, ITN ordering, sandbox tunnel setup, and handling late payments that require a manual refund.

## Calendar, analytics, customers, and audit (slice 8)

Owner endpoints are scoped to the business in the URL; missing or cross-business access returns 404. Staff may read only their own calendar column. All date ranges are inclusive business-local dates, with a maximum of 366 days. Aggregates and timeseries are calculated in SQL; timeseries buckets are zero-filled. A zero previous-period value produces a `null` percentage change instead of division by zero. Funnel outcomes report database booking states only; page-view and booking-start funnel steps are not tracked.

- `GET /api/admin/businesses/{id}/calendar?date=YYYY-MM-DD` returns staff working windows, time off, and that day's bookings.
- `GET /api/admin/businesses/{id}/calendar/week?start=YYYY-MM-DD` returns a seven-day count of bookings and open service slots per staff member.
- `GET /api/admin/businesses/{id}/analytics/summary?from=&to=` returns bookings, revenue (the sum of `price_cents` for completed bookings), expected revenue (the sum of `price_cents` for confirmed bookings whose start is still in the future), paid deposits, fill/no-show/cancellation rates, equal-length previous-period values, and percent changes.
- `GET /api/admin/businesses/{id}/analytics/timeseries?metric=bookings|revenue&interval=day|week&from=&to=`; `status-mix`, `heatmap`, `utilisation`, and `outcomes` accept `from` and `to`.
- `GET /api/admin/businesses/{id}/customers?search=&sort=&limit=&offset=` and `/customers/{user_id}` show customers and only their history at this business. Search treats `%`, `_`, and backslash literally.
- `GET /api/admin/businesses/{id}/audit-log` accepts `entity`, `actor`, `from`, `to`, `limit`, and `offset`. Secret fields and raw payment payloads are excluded.

`flask seed-demo [--reset]` creates deterministic Fade Lab Barbers sample data in non-production environments. Demo credentials are configured with `DEMO_OWNER_EMAIL`, `DEMO_OWNER_PASSWORD`, and `DEMO_OWNER_NAME`; defaults are for local demos only.

## Registered route coverage

The following additional concrete paths complete the route inventory. `business_id`, `service_id`, `staff_id`, `time_off_id`, and `user_id` are integer path parameters.

| Method | Path | Purpose / access |
| --- | --- | --- |
| PATCH | `/api/admin/businesses/{business_id}/services/{service_id}` | Update an owner-scoped service |
| POST | `/api/admin/businesses/{business_id}/services/{service_id}/deactivate` | Deactivate an owner-scoped service |
| PATCH | `/api/admin/businesses/{business_id}/staff/{staff_id}` | Update an owner-scoped staff member |
| POST | `/api/admin/businesses/{business_id}/staff/{staff_id}/deactivate` | Deactivate an owner-scoped staff member |
| POST, DELETE | `/api/admin/businesses/{business_id}/staff/{staff_id}/services/{service_id}` | Assign or remove a staff service |
| GET, PUT | `/api/admin/businesses/{business_id}/staff/{staff_id}/working-hours` | Read or replace working hours |
| GET, POST | `/api/admin/businesses/{business_id}/staff/{staff_id}/time-off` | List or create time off |
| DELETE | `/api/admin/businesses/{business_id}/staff/{staff_id}/time-off/{time_off_id}` | Remove time off |
| GET | `/api/b/{slug}/staff` | List active public staff |
| GET | `/api/admin/businesses/{business_id}/analytics/status-mix` | Booking status aggregate |
| GET | `/api/admin/businesses/{business_id}/analytics/heatmap` | Weekday and hour aggregate |
| GET | `/api/admin/businesses/{business_id}/analytics/utilisation` | Staff utilisation aggregate |
| GET | `/api/admin/businesses/{business_id}/analytics/outcomes` | Booking outcome aggregate |
| GET | `/api/admin/businesses/{business_id}/customers/{user_id}` | Read this business's customer history |
