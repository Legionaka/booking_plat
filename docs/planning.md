# Booking Platform: Product, Schema and Design Plan

Prepared for Legion Cunningham, November 2026

## 1. End goal

A deployed, multi-tenant booking platform where small businesses (barbers, clinics, tutors) set up services and working hours, and customers book, pay a deposit and get reminders. No double-bookings, no admin back-and-forth. One deployment serves many businesses, each with its own page at `/b/<slug>`.

**What it proves to a hiring team:** relational design, concurrency control, state machines, background jobs, third-party integration (PayFast), security, testing, CI/CD and deployment, plus a polished product UI.

**Success criteria for the portfolio version**

- Live URL with a seeded demo business and a demo login
- A README with architecture diagram, screenshots and a trade-offs section
- Tests on the availability engine and the booking flow, running in CI
- A concurrency test that proves two simultaneous requests cannot book the same slot

## 2. Roles

| Role | Can do |
| --- | --- |
| Customer | Browse services, book, pay a deposit, reschedule or cancel, see history |
| Staff | See their own calendar, mark bookings completed or no-show |
| Owner | Manage services, staff, hours, time off, pricing, bookings and reports |
| Platform admin | Manage businesses and monitor the system (you) |

## 3. Features by tier

**v1 (MVP, deployable)**

- Register, login, logout, email verification, password reset
- Services with duration, buffer time and price
- Weekly working hours per staff member, plus time off
- Availability engine: service + staff + date returns open slots
- Booking flow: pick service, pick time, confirm
- Cancel and reschedule with a cutoff rule (default 24 hours)
- Owner dashboard: day calendar and booking list
- Confirmation emails

**v2 (real product layer)**

- PayFast sandbox deposits with validated ITN webhooks
- Reminders at 24 hours and 2 hours before, sent from a background queue
- Multiple staff with their own schedules and service assignments
- Waitlist: a cancelled slot notifies the next person
- Customer history and a no-show counter

**v3 (industry polish)**

- Multi-tenant branding and per-business slugs
- Audit log of who changed what and when
- Analytics: bookings per week, revenue, busiest times, no-show rate
- Public REST API with API keys and OpenAPI docs
- WhatsApp or SMS reminders
- Google Calendar sync (OAuth)
- Installable PWA

## 4. Stack and architecture

| Layer | Choice |
| --- | --- |
| Backend | Flask with blueprints, SQLAlchemy, Alembic migrations, Pydantic validation |
| Database | PostgreSQL |
| Queue | Redis with RQ (or Celery) for emails and reminders |
| Frontend | Vanilla HTML, CSS and JS consuming the JSON API |
| Email | Resend or SMTP |
| Payments | PayFast sandbox |
| Infra | Docker, docker-compose, GitHub Actions CI, Render, Railway or Fly.io |
| Observability | Structured logs, a `/health` endpoint, Sentry free tier |

```
Browser (customer page / owner dashboard)
        |  JSON over HTTPS
Flask API  ----  PostgreSQL (source of truth, constraints)
        |
      Redis ---- Worker (reminders, emails, hold expiry)
        |
   PayFast (ITN webhook)   Email provider
```

## 5. Database schema (PostgreSQL)

This refines the earlier sketch: roles now live in a `memberships` table, so one person can be a customer at one business and staff at another.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE businesses (
  id                  BIGSERIAL PRIMARY KEY,
  slug                CITEXT UNIQUE NOT NULL,
  name                TEXT NOT NULL,
  timezone            TEXT NOT NULL DEFAULT 'Africa/Johannesburg',
  cancel_cutoff_hours INT  NOT NULL DEFAULT 24,
  slot_step_min       INT  NOT NULL DEFAULT 15,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  email         CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name     TEXT NOT NULL,
  phone         TEXT,
  verified_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('owner','staff')),
  PRIMARY KEY (user_id, business_id)
);

CREATE TABLE staff (
  id           BIGSERIAL PRIMARY KEY,
  business_id  BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  user_id      BIGINT REFERENCES users(id),
  display_name TEXT NOT NULL,
  active       BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE services (
  id            BIGSERIAL PRIMARY KEY,
  business_id   BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  duration_min  INT  NOT NULL CHECK (duration_min > 0),
  buffer_min    INT  NOT NULL DEFAULT 0 CHECK (buffer_min >= 0),
  price_cents   INT  NOT NULL CHECK (price_cents >= 0),
  deposit_cents INT  NOT NULL DEFAULT 0 CHECK (deposit_cents >= 0),
  active        BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE staff_services (
  staff_id   BIGINT REFERENCES staff(id) ON DELETE CASCADE,
  service_id BIGINT REFERENCES services(id) ON DELETE CASCADE,
  PRIMARY KEY (staff_id, service_id)
);

CREATE TABLE working_hours (
  id         BIGSERIAL PRIMARY KEY,
  staff_id   BIGINT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  weekday    SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time   TIME NOT NULL,
  CHECK (end_time > start_time)
);

CREATE TABLE time_off (
  id       BIGSERIAL PRIMARY KEY,
  staff_id BIGINT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  during   TSTZRANGE NOT NULL,
  reason   TEXT
);

CREATE TABLE bookings (
  id              BIGSERIAL PRIMARY KEY,
  business_id     BIGINT NOT NULL REFERENCES businesses(id),
  customer_id     BIGINT NOT NULL REFERENCES users(id),
  staff_id        BIGINT NOT NULL REFERENCES staff(id),
  service_id      BIGINT NOT NULL REFERENCES services(id),
  start_at        TIMESTAMPTZ NOT NULL,
  end_at          TIMESTAMPTZ NOT NULL,
  blocked_until   TIMESTAMPTZ NOT NULL,          -- end_at + buffer
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','confirmed','cancelled','completed','no_show')),
  hold_expires_at TIMESTAMPTZ,                   -- pending holds expire
  price_cents     INT NOT NULL,                  -- snapshot at booking time
  deposit_cents   INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_at > start_at AND blocked_until >= end_at),
  EXCLUDE USING gist (
    staff_id WITH =,
    tstzrange(start_at, blocked_until, '[)') WITH &&
  ) WHERE (status IN ('pending','confirmed'))
);
CREATE INDEX bookings_business_start ON bookings (business_id, start_at);
CREATE INDEX bookings_customer ON bookings (customer_id);

CREATE TABLE payments (
  id           BIGSERIAL PRIMARY KEY,
  booking_id   BIGINT NOT NULL REFERENCES bookings(id),
  provider     TEXT NOT NULL,
  provider_ref TEXT NOT NULL,
  amount_cents INT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('pending','paid','failed','refunded')),
  raw_payload  JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_ref)               -- makes webhook handling idempotent
);

CREATE TABLE notifications (
  id            BIGSERIAL PRIMARY KEY,
  booking_id    BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,                  -- confirmation, reminder_24h, reminder_2h, waitlist
  scheduled_for TIMESTAMPTZ NOT NULL,
  sent_at       TIMESTAMPTZ,
  status        TEXT NOT NULL DEFAULT 'queued',
  UNIQUE (booking_id, kind)
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  business_id BIGINT REFERENCES businesses(id),
  actor_id    BIGINT REFERENCES users(id),
  entity      TEXT NOT NULL,
  entity_id   BIGINT NOT NULL,
  action      TEXT NOT NULL,
  diff        JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design decisions worth explaining in interviews**

- **Double-booking is blocked by the database.** The exclusion constraint rejects overlapping `pending` or `confirmed` bookings for the same staff member, so two simultaneous requests cannot both succeed. The app catches the constraint error and shows a friendly message.
- **All times are stored in UTC** (`TIMESTAMPTZ`) and converted to the business timezone only at the edges.
- **Money is integer cents**, and prices are snapshotted on the booking so later price changes do not rewrite history.
- **Pending holds expire.** A worker cancels expired holds, otherwise unpaid bookings would block slots forever.
- **Unique keys make jobs idempotent:** `(provider, provider_ref)` for payments and `(booking_id, kind)` for notifications mean a retried webhook or job cannot duplicate anything.
- **Every tenant-owned query is scoped by `business_id`.** Add a test that tries to read another business's data and expects a 404.

## 6. Booking state machine

| From | To | Trigger |
| --- | --- | --- |
| (new) | pending | Customer picks a slot (deposit required) |
| (new) | confirmed | Customer picks a slot (no deposit) |
| pending | confirmed | Payment received, or owner confirms |
| pending | cancelled | Hold expires or customer cancels |
| confirmed | cancelled | Customer or owner cancels (cutoff rules apply to customers) |
| confirmed | completed | Staff marks done |
| confirmed | no\_show | Staff marks no-show after the start time |

Anything else is rejected in code with a clear error. Keep the transitions in one function so they are easy to test.

## 7. Availability engine

This is the heart of the app, so build and test it first.

```
get_slots(business, service, staff, date):
    tz        = business.timezone
    windows   = working_hours for staff on weekday(date), as datetimes in tz
    blocked   = time_off overlapping date
              + bookings (pending/confirmed) overlapping date, using start_at..blocked_until
    free      = windows minus blocked          # interval subtraction
    slots     = []
    for each free interval:
        t = interval.start
        while t + service.duration + service.buffer <= interval.end:
            slots.append(t)
            t += business.slot_step_min
    drop slots earlier than now + minimum_notice
    return slots converted to UTC
```

**Edge cases to write tests for:** a booking straddling midnight, daylight-saving boundaries (South Africa has none, but the code should not assume that), buffers between back-to-back bookings, time off covering part of a day, a service longer than any free gap, and a staff member who does not offer the service.

## 8. API outline

| Method and path | Purpose |
| --- | --- |
| POST `/api/auth/register`, `/login`, `/logout` | Authentication |
| POST `/api/auth/verify`, `/reset` | Email verification and password reset |
| GET `/api/b/<slug>/services` | Public service list |
| GET `/api/b/<slug>/slots?service=&staff=&date=` | Available slots |
| POST `/api/b/<slug>/bookings` | Create a booking (409 if the slot was just taken) |
| PATCH `/api/bookings/<id>` | Reschedule, cancel, or change status (role-checked) |
| GET `/api/me/bookings` | Customer history |
| GET/POST `/api/admin/services`, `/staff`, `/hours`, `/time-off` | Owner management |
| GET `/api/admin/bookings?from=&to=` | Calendar data |
| POST `/api/payments/payfast/itn` | PayFast webhook (signature-validated, idempotent) |
| GET `/health` | Liveness and database check |

Use consistent error shapes (`{ "error": { "code", "message" } }`), pagination on list endpoints, and rate limiting on login and booking creation.

## 9. Project structure

```
booking-platform/
  AGENTS.md                     # read first: stack, rules, Figma source of truth, build order
  README.md
  docs/
    design/
      figma.md                  # file link, page and frame map, screen-to-route table
      design-tokens.md          # Figma variables mapped to CSS custom properties
      screens.md                # every screen: route, API calls, states
    api.md                      # endpoint list, error shape
    schema.sql                  # the schema from section 5
  app/
    __init__.py  config.py  extensions.py
    models/  schemas/  services/  jobs/
    blueprints/                 # auth, public, customer, admin, platform, payments
    templates/
      base.html                 # fonts, shared document shell
      auth/                     # sign in, register, reset, verify, invite, 2FA, onboarding
      customer/                 # landing, booking flow, my bookings, booking detail
      owner/                    # dashboard, calendar, services, staff, hours, customers,
                                # payments, analytics, settings, audit log
      platform/                 # businesses, system health
      emails/                   # confirmation, reminder, cancellation
      errors/                   # 404, 500, offline
      dev/components.html       # living component sheet, every component in every state
    static/
      css/
        tokens.css              # :root variables from section 13
        base.css  glass.css  typography.css  layout.css
        components/             # slot.css  button.css  badge.css  modal.css  toast.css
                                # booking-block.css  kpi-card.css  chart-card.css
      js/
        main.js                 # shared helpers
        api.js                  # fetch wrapper, error handling
        components/             # slot-picker.js  availability-strip.js  command-palette.js
                                # drawer.js  toast.js  timeline.js
        charts/                 # sparkline.js  area.js  bars.js  donut.js  heatmap.js
                                # rings.js  funnel.js  (hand-written SVG, no chart library)
        pages/                  # one script per page
      assets/                   # SVG icons, favicon, social image
  migrations/
  tests/
    unit/  integration/  concurrency/
  docker-compose.yml  Dockerfile  .env.example
  .github/workflows/ci.yml
```

Keep routes thin and put logic in `services/`. That separation is what makes the code testable and is a strong signal in code review.

## 10. Security and quality checklist

- Password hashing with argon2 or bcrypt, never plain or fast hashes
- CSRF protection, secure and HttpOnly session cookies, rate limiting on auth endpoints
- Role checks on every admin route and `business_id` scoping on every query
- Server-side validation of every input, including dates and IDs
- PayFast ITN: verify the signature, confirm the amount, and handle repeats safely
- Secrets only in environment variables, with a committed `.env.example`
- `pytest` suite with coverage on services, run in GitHub Actions on every push
- Linting and formatting (ruff, black), type hints on service code
- Structured logging with request IDs, and no personal data in logs
- Database backups noted in the README, even for the demo

## 11. Build order and skills progression

| Phase | Build | Skills you prove |
| --- | --- | --- |
| 1 | Schema, migrations, auth, services, working hours | Relational design, migrations, security basics |
| 2 | Availability engine and booking flow | Algorithmic thinking, timezones, edge-case testing |
| 3 | Double-booking constraint, cancel and reschedule rules | Concurrency, transactions, state machines |
| 4 | Customer booking page, owner and staff workspace | Frontend architecture, API consumption, data visualization |
| 5 | Email and reminders through the queue | Background jobs, retries, idempotency |
| 6 | PayFast deposits and webhooks | Third-party integration, signature verification |
| 7 | Docker, CI, deployment, monitoring | DevOps fundamentals |
| 8 | Multi-tenancy polish, audit log, analytics | System design, data isolation |
| 9 | Public API, OpenAPI docs, Google Calendar OAuth | API design, OAuth |

Phase 4 owner and staff screens are implemented against the existing admin, calendar, payments, and analytics APIs. The walk-in booking frame is deferred because the booking relation requires a registered customer; see [ADR 0005](decisions/0005-walk-in-booking.md). Detailed page routes and frame IDs are in [design/screens.md](design/screens.md). The remaining roadmap here is consolidated and corrected in the documentation phase.

## 12. Future updates

- Recurring appointments and packages (for example, 5 lessons for a tutor)
- Customer reviews after completed bookings
- Per-service staff pricing and promo codes
- Refund flow tied to the cancellation policy
- Multi-location businesses
- Admin impersonation with audit trail for support
- Move reminders to webhooks plus a WhatsApp provider
- Load testing (Locust or k6) and a short write-up of the results
- Optional rewrite of one service in FastAPI with async I/O, to show range

## 13. Frontend design system: flat monochrome glass

The product uses a flat, dark monochrome interface. Figma is the layout and typography reference; this global style rule removes every gradient treatment.

### Surfaces and color

- Page backgrounds use solid Obsidian. There is no ambient light layer or drift animation.
- Glass uses a translucent white fill, a 1 px solid hairline border, and backdrop blur. Graphite remains the solid fallback when blur is unavailable.
- Primary buttons and selected slots use flat Pearl with Obsidian text. A selected slot has a 2 px Pearl ring and no colored glow.
- Amber, Jade, and Rose are reserved for booking status. Other interface surfaces use the monochrome palette in `app/static/css/tokens.css`.
- No CSS gradients, SVG gradient paints, mask fades, gradient-clipped text, or pointer-following sheen are allowed. `scripts/check_frontend_policy.py` enforces this in templates and static assets.

### Type, shape, and motion

- Headings use self-hosted Bricolage Grotesque; interface text uses self-hosted Instrument Sans.
- Tabular figures are used for times, prices, and data labels.
- Radius roles are 28 px panels, 20 px cards, 14 px controls, 12 px slot keys, and full pills for badges and toggles.
- Ordinary hover, press, focus, and state transitions remain. Respect `prefers-reduced-motion`; keep focus rings visible and tap targets at least 44 px.

### Charts

Charts are hand-written SVG with solid strokes and fills at fixed opacity. Heatmaps use five discrete flat steps from graphite to white. Donut segments, bars, and status marks use flat palette colors. Every chart needs an accessible name and empty or insufficient-data states.

### Layout

Customer booking prioritizes the service choice, availability strip, selectable time slots, and booking summary. Owner views prioritize the calendar, status, and business metrics. Match spacing, radii, type, and copy to Figma; document any behavior-driven visual override in `docs/design/figma.md`.

### Interface copy

Write from the customer's point of view, in sentence case, with the same name for an action through the whole flow.

- Button: **Confirm booking**, then the toast says **Booking confirmed**
- Cancel: **Cancel booking**, then **Booking cancelled**
- Slot taken: **That time was just booked. Pick another slot.**
- Late cancellation: **This booking starts in under 24 hours, so it can't be cancelled online. Contact the business to change it.**
- Empty day (owner): **No bookings today. Share your booking link to get your first one.**
- Chart with too little data: **Not enough bookings yet. Charts fill in after your first week.**

## 14. README checklist

- One-paragraph pitch and a live demo link with demo credentials
- Screenshots or a short GIF of the booking flow and the dashboard
- Architecture diagram and the schema diagram
- Setup in under five commands (`docker compose up`)
- A design decisions section covering the exclusion constraint, UTC storage, idempotent webhooks and tenant scoping
- Test instructions and a CI badge
- A short list of what you would build next

## 15. Design source and handoff to Codex

The screens are designed in Figma, and Codex builds the frontend from that file plus this doc. Figma is the source of truth for how things look. This doc is the source of truth for behavior, data and rules. If they disagree on a visual detail, Figma wins; if they disagree on behavior, this doc wins, and the difference gets noted in `docs/design/figma.md`.

### Design source

| Item | Value |
| --- | --- |
| Figma file | [Booking platform design](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=20-837) |
| Design system page | `Design system` (tokens, glass depths, slot key states, components, chart styles) |
| Customer portal frames | `<PAGE_NAME>` |
| Owner and staff portal frames | `<PAGE_NAME>` |
| Platform admin frames | `<PAGE_NAME>` |
| Auth and onboarding frames | `F • Authentication and onboarding` (see `docs/design/figma.md`) |
| System states and emails | `<PAGE_NAME>` |
| Prototype flows | Book end to end, cancel a late booking, owner confirms and completes, owner explores analytics, owner sign in, forgot password, staff accepts invite, owner onboarding |

Verification and reset links are frontend routes at `/auth/verify?token=...` and `/auth/reset?token=...`, built from `PUBLIC_BASE_URL`. These links must never expose a password.

For the file to be usable by Codex: name frames as `Portal / Screen / State`, keep colors, type, radius and blur as Figma variables, give the share link view access, and turn on Dev Mode (or the Figma MCP server) so Codex can read the file directly.

### Screen inventory

| Group | Routes | Templates | Main API calls |
| --- | --- | --- | --- |
| Customer booking | `/b/<slug>`, `/b/<slug>/book`, `/b/<slug>/book/time`, `/b/<slug>/book/pay`, `/b/<slug>/book/confirmed/<id>`, `/b/<slug>/waitlist` | `customer/` | services, slots, create booking, payments |
| Customer account | `/account/bookings`, `/account/bookings/<id>`, `/account/security` | `customer/`, `auth/` | my bookings, booking update, sessions |
| Auth | `/auth/login`, `/auth/register`, `/auth/verify`, `/auth/forgot`, `/auth/reset/<token>`, `/auth/invite/<token>`, `/auth/2fa` | `auth/` | auth endpoints |
| Owner onboarding | `/app/onboarding` | `auth/` | business, services, hours, staff |
| Owner and staff | `/app`, `/app/week`, `/app/services`, `/app/staff`, `/app/hours`, `/app/customers`, `/app/payments`, `/app/analytics`, `/app/settings`, `/app/audit` | `owner/` | admin endpoints, bookings, analytics |
| Platform admin | `/platform/businesses`, `/platform/businesses/<id>`, `/platform/health` | `platform/` | platform endpoints |
| System | 404, 500, offline | `errors/` | none |
| Emails | confirmation, 24-hour reminder, cancellation | `emails/` | rendered by jobs |

The command palette, booking detail drawer and toasts are shared components, not routes.

### Figma to code rules

- Frontend is vanilla HTML, CSS and JS only. No React, Tailwind or charting library. Charts are hand-written SVG modules in `app/static/js/charts/`.
- Every Figma variable becomes a CSS custom property in `tokens.css` (the file in section 13 is the starting point). Components never hard-code hex values, radii or blur amounts.
- Add a blur token (`--blur-glass: 28px`) and any spacing tokens that the Figma file defines.
- Build each Figma component once as a CSS component plus a template partial, and reuse it. The slot key, glass panel, status badge, KPI card, chart card, booking block and drawer are the core set.
- Match spacing, radii, blur and all states (default, hover, focus, selected, disabled, loading, empty, error). If Figma lacks a state, extend the nearest existing pattern and list it in `docs/design/figma.md`.
- Do not introduce colors outside the palette. Amber, Jade and Rose are for booking status only.
- Every glass surface keeps a solid fallback, keyboard focus rings stay visible, tap targets are at least 44 px, and `prefers-reduced-motion` is respected.

### Token mapping (Figma variable to CSS)

| Figma variable | CSS custom property |
| --- | --- |
| color/obsidian, color/graphite | `--obsidian`, `--graphite` |
| color/glass-fill, glass-border | `--glass`, `--glass-border` |
| color/pearl, silver, fog, dim, steel | `--pearl`, `--silver`, `--fog`, `--dim`, `--steel` |
| color/amber, jade, rose | `--amber`, `--jade`, `--rose` |
| radius/panel, card, control, slot | `--r-panel`, `--r-card`, `--r-control`, `--r-slot` |
| type/display, type/ui | `--font-display`, `--font-ui` |
| blur/glass | `--blur-glass` |

### Frontend build order for Codex

1. `tokens.css`, `base.css`, `glass.css` and `base.html` (flat surfaces, fonts).
2. The living component sheet at `/dev/components`, with every component in every state.
3. Auth screens.
4. Customer booking flow: slot picker, availability strip, confirmation.
5. Owner dashboard: KPI cards, day timeline, SVG charts.
6. Remaining owner and staff screens.
7. Platform admin, system states and email templates.

Backend work follows the phases in section 11. The availability engine and booking endpoints should exist before screens 4 and 5 are wired to real data; until then, use fixture JSON that matches the API shapes.

### AGENTS.md draft

Copy this into the repo root and fill in the Figma link.

```markdown
# AGENTS.md

## Project
Multi-tenant booking platform for small businesses (barbers, clinics, tutors).
Stack: Flask, PostgreSQL, Redis with RQ, vanilla HTML/CSS/JS frontend.
Planning doc: <PLANNING_DOC_URL>

## Sources of truth
- Visual design: the Figma file at <FIGMA_FILE_URL>. Figma wins on how things look.
- Frame-to-route map: docs/design/figma.md
- Behavior, data and rules: the planning doc, docs/schema.sql and docs/api.md.

## Backend rules
- Python, Flask blueprints, SQLAlchemy, Alembic migrations, Pydantic validation.
- Keep routes thin. Business logic lives in app/services.
- Store all times in UTC. Store money as integer cents.
- Scope every tenant-owned query by business_id.
- Double-booking is prevented by the database exclusion constraint. Catch the error and return 409.
- Webhooks and jobs must be idempotent.

## Frontend rules
- Vanilla HTML, CSS and JS only. No frameworks, no Tailwind, no chart library.
- Charts are hand-written SVG in static/js/charts.
- All colors, radii, blur and fonts come from app/static/css/tokens.css. Never hard-code them.
- Theme: dark, black, glassy, silver. Monochrome. Amber, Jade and Rose are for booking status only. No purple.
- Every glass surface needs a solid fallback. Respect prefers-reduced-motion. Keep focus rings visible and tap targets at least 44 px.
- Match Figma spacing, radii and states. If a state is missing in Figma, extend the nearest pattern and note it in docs/design/figma.md.

## Workflow
- Follow the build order in the planning doc (backend phases and frontend order).
- Work on one feature at a time and write tests with it.
- Run pytest and ruff before finishing a task.
- Ask before adding a dependency or changing the schema. Schema changes need a migration.

## Never
- Commit secrets. Use environment variables and keep .env.example current.
- Skip input validation or role checks.
- Introduce colors outside the palette.
```
