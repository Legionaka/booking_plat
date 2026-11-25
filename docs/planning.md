# Product plan: current build and roadmap

## Product

Multi-tenant appointment booking for small businesses. Customers find a service and available time, book, pay a deposit through PayFast when required, and manage appointments. Owners and staff manage only their permitted workspace. PostgreSQL is the source of truth for bookings and payments; Redis supports sessions, rate limits, and background work.

## Implemented

- Authentication, email verification and password reset, server-side sessions, CSRF, role-based memberships.
- Business/service catalog, staff assignment, weekly hours, time off, timezone-aware availability, booking creation, cancellation, rescheduling.
- PostgreSQL exclusion constraint for active booking overlaps; conflicts become HTTP 409.
- PayFast checkout handoff, signed ITN validation, idempotent payment updates, sandbox mode, and status polling.
- Transactional email outbox, console/SMTP/HTTPS delivery, RQ worker, scheduler, and reminders.
- Public platform landing page; customer booking/account screens; owner onboarding, dashboard, week calendar, bookings, services, staff, hours, customers, payments, analytics, settings/QR, and audit log.
- Docker Compose, Render blueprint, CI, demo seed, unit/integration/contract/browser test suites.

See [API](api.md), [architecture](architecture.md), [screens](design/screens.md), and [testing](testing.md).

## System rules

1. Store timestamps as UTC instants. Interpret local dates and working windows in the business IANA timezone.
2. Store currency as integer cents and snapshot booking prices.
3. Scope tenant-owned queries by business. Scope staff calendar reads to linked staff records.
4. Enforce overlap and idempotency in PostgreSQL as well as application logic.
5. Commit notification intent with booking/payment state, then deliver asynchronously.
6. Use vanilla HTML/CSS/JS and the flat monochrome tokens documented in `design/design-tokens.md`.

## Phase status

| Phase | Status | Notes |
| --- | --- | --- |
| 0 | Complete | Flat-style enforcement, repository hygiene, and baseline contracts. |
| 1 | Complete | SMTP plus HTTPS email providers behind a common interface. |
| 2 | Complete | Shared components, component sheet, error states, keyboard behavior. |
| 3 | Complete | Customer booking portal and payment states. |
| 4 | Complete | Owner/staff workspace. Walk-in screen deferred; see [ADR 0005](decisions/0005-walk-in-booking.md). |
| 5 | Complete | Documentation, portfolio readiness, coverage and accessibility quality gates. |
| 6 | Parked | Invitations, TOTP, session list, business switcher, platform admin, waitlist. |
| 7 | Not started | Clean-clone regression and handover. |

## Deferred work and limits

- Walk-in booking: bookings currently require a registered customer. No existing table was changed; defer the UI until customer identity semantics are decided.
- Waitlist, staff invitations, TOTP, active-session UI, business switcher, and platform-admin screens are Phase 6.
- Refunds are manual. Late payment after cancellation needs operator review.
- Registration intentionally reports duplicate addresses; this allows account enumeration.
- SMS/WhatsApp, calendar sync, PWA, multi-location, recurring appointments, packages, and automated refunds remain roadmap ideas.

## Visual system (replacement for the original section 13)

Surfaces use solid Obsidian; glass uses translucent fill, a 1 px border, and a solid fallback. Primary buttons and selected slots use Pearl. Booking status colors are reserved for status. Charts use solid SVG fills/strokes and five discrete heatmap steps. Gradients, gradient SVG paints, masks/fades, gradient text, ambient light, and pointer-following sheen are disallowed. Motion respects reduced-motion preferences. See [Figma overrides](design/figma.md) and [tokens](design/design-tokens.md).
