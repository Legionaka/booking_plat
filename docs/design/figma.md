# Figma handoff

## Source of truth

- Figma is the source of truth for visual design. The product plan is the source of truth for behavior, data, and business rules.
- Project Figma file: [Booking platform design](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=20-837).
- The file is readable. Design system page: `Design system`; auth page: `F • Authentication and onboarding`.
- If Figma and the product plan differ visually, follow Figma. If they differ on behavior, follow the product plan and record the discrepancy here.

## Figma organization

The file has these confirmed pages:

| Area | Figma page/frame | Status |
| --- | --- | --- |
| Design system | `Design system` page; `Fade Lab • Design system` frame, node `2:121` | Verified; color tokens, ambient glass, typography, interactive components |
| Customer portal | `Customer • Book in a minute` and `Customer • Desktop and tablet` | Verified; implemented in Phase 3 at mobile, tablet, and desktop widths; see [screens.md](screens.md) |
| Owner and staff portal | `Owner • Live control room` (`2:1014`) and `Responsive • Owner and system states` (`2:4670`) | Verified; implemented in Phase 4 at 390, 820, and 1440 px; see [screens.md](screens.md) |
| Platform admin | `Platform admin • Operations` | Verified; admin sign-in frame has no matching backend role/route |
| Authentication and onboarding | `F • Authentication and onboarding`, node `20:837` | Verified; full 181-frame index in [auth-frame-inventory.md](auth-frame-inventory.md) |
| Emails | `Emails • Transactional` | Verified; outside F1 |

## Screen-to-route map

F1 route mapping and implemented template:

| Area | Route(s) | Template group | Main API calls |
| --- | --- | --- | --- |
| Customer booking | `/b/<slug>`, `/b/<slug>/book`, `/b/<slug>/book/time`, `/b/<slug>/book/pay`, `/b/<slug>/book/confirmed/<id>`, `/b/<slug>/waitlist` | `customer/` | Public services, availability slots, booking creation, payments |
| Customer account | `/account/bookings`, `/account/bookings/<id>`, `/account/security` | `customer/`, `auth/` | Customer bookings, booking updates, sessions |
| Authentication | `/auth/login`, `/auth/register`, `/auth/verify`, `/auth/forgot`, `/auth/reset/<token>`, `/auth/invite/<token>`, `/auth/2fa` | `auth/` | Authentication endpoints |
| F1 customer/business auth | `/auth/login`, `/auth/register`, `/auth/verify`, `/auth/forgot`, `/auth/forgot/sent`, `/auth/reset` | `auth/login.html`, `register.html`, `verify.html`, `forgot.html`, `forgot_sent.html`, `reset.html` | CSRF, register, login, me, verify, resend, forgot, reset |
| F1 signed-in placeholders | `/account`, `/app` | `auth/placeholder.html` plus `components/session_expired.html` | me, logout |
| F1 component sheet | `/dev/components` | `dev/components.html` plus `components/` partials | None |
| Owner onboarding | `/app/onboarding` | `auth/` | Business, services, staff, and hours management |
| Owner and staff | `/app`, `/app/week`, `/app/services`, `/app/staff`, `/app/hours`, `/app/customers`, `/app/payments`, `/app/analytics`, `/app/settings`, `/app/audit` | `owner/` | Admin endpoints, bookings, analytics |
| Platform admin | `/platform/businesses`, `/platform/businesses/<id>`, `/platform/health` | `platform/` | Platform endpoints |
| System states | 404, 500, offline | `errors/` | None |
| Emails | Confirmation, 24-hour reminder, cancellation | `emails/` | Rendered by background jobs |

The command palette, booking detail drawer, and toasts are shared components, not routes.

## Design tokens

Map Figma variables to CSS custom properties in `app/static/css/tokens.css`:

| Figma variable | CSS property |
| --- | --- |
| `color/obsidian`, `color/graphite` | `--obsidian`, `--graphite` |
| `color/glass-fill`, `color/glass-border` | `--glass`, `--glass-border` |
| `color/pearl`, `color/silver`, `color/fog`, `color/dim`, `color/steel` | `--pearl`, `--silver`, `--fog`, `--dim`, `--steel` |
| `color/amber`, `color/jade`, `color/rose` | `--amber`, `--jade`, `--rose` |
| `radius/panel`, `radius/card`, `radius/control`, `radius/slot` | `--r-panel`, `--r-card`, `--r-control`, `--r-slot` |
| `type/display`, `type/ui` | `--font-display`, `--font-ui` |
| `blur/glass` | `--blur-glass` |

The plan's starting theme is Obsidian `#050506`, Graphite `#0E0F12`, Pearl `#F5F6F8`, Silver `#C4C9D4`, Fog `#9298A6`, Dim `#7A8090`, Steel `#8A93A6`, Amber `#E3B25C`, Jade `#4ADE9F`, and Rose `#FF6B8A`. Amber, Jade, and Rose are reserved for booking status. Confirm final values and spacing tokens against Figma.

### Current implementation checkpoint

F1 values have been reconciled with Figma. See [design-tokens.md](design-tokens.md) for the variable values and exact CSS changes. The backend rule is 10 to 128 characters; the Figma password helper copy needs to change from 12 to 10 characters.

### F1 deferred states

Do not implement guest checkout, social/Google sign-in, staff invite acceptance, two-step verification or backup codes, session listing, or platform-admin sign-in in F1. The backend has no matching route/role for these screens. Lockout has no distinct backend response today; the shared login error handles supported responses. Each frame is listed with route/template status in [auth-frame-inventory.md](auth-frame-inventory.md).

Flat-style override: the global product rule removes gradients, SVG gradient paints, mask fades, gradient-clipped text, ambient light fields and drift, top-edge glass fades, inner glows, colored slot glows, and pointer-following sheen. Glass retains a translucent white fill, solid 1 px hairline, and blur with a Graphite fallback. Primary buttons and selected slots use flat Pearl; selected slots have a 2 px Pearl ring. Charts use solid strokes and fills, with five discrete heatmap steps. Ordinary hover, press, focus, and reduced-motion behavior remain. The Figma layer named “Violet light field” is omitted; it is not rendered as a product surface. No auth artwork requires imported assets or CSP exceptions.

## Responsive auth layout decisions

- The auth canvas is capped at 1920 px on ultra-wide screens. Its desktop columns remain balanced; the form card stays near Figma's 440 px width.
- At 820 px and below the auth view is a single column and hides the ambient preview. At 390 px the card is 366 px wide to satisfy the minimum tested width while keeping 12 px side gutters; Figma's sample is 358 px wide.
- The registration frame has no right-side preview, so its ambient panel is omitted. Customer sign-in keeps the Figma service list and availability chart; the business portal uses its next-appointment preview.
- At desktop heights below 960 px the ambient content compacts so the chart and footer remain visible. The 820 × 1180 layout uses the centered single-column form pattern.

## Implementation rules

- Use vanilla HTML, CSS, and JavaScript. Do not add a frontend framework, Tailwind, or a charting library.
- Implement charts as hand-written SVG modules in `app/static/js/charts/`.
- Implement each shared component once as a CSS component and reusable template partial.
- Match spacing, radii, blur, and the default, hover, focus, selected, disabled, loading, empty, and error states.
- If Figma omits a state, extend the closest established pattern and document the decision in this file.
- Every glass surface needs a solid fallback. Preserve visible keyboard focus, 44 px minimum tap targets, and `prefers-reduced-motion` support.
- Do not introduce colors outside the defined palette.

## Frontend build order

1. `tokens.css`, `base.css`, `glass.css`, and `base.html`.
2. Living component sheet at `/dev/components`, covering every component state.
3. Authentication screens.
4. Customer booking flow: slot picker, availability strip, confirmation.
5. Owner dashboard: KPI cards, day timeline, SVG charts.
6. Remaining owner and staff screens.
7. Platform admin, system states, and email templates.

## Phase 2 component coverage

The Design system page's component and data-state frames are represented on `/dev/components`: `Fade Lab • Design system` (`2:121`), `Charts • SVG library and data states` (`2:281`), and `Solid fallback • Accessible surfaces` (`2:8789`). Reusable markup is in `components/ui.html`; visual styles are in `static/css/components/system.css` and use the shared token palette.

| Figma concept | Implemented pattern | State coverage |
|---|---|---|
| Buttons and selected slot | `button.html`, `ui.html` slot key | Ready, hover, keyboard focus, selected, disabled, loading |
| Status and form controls | status badge, labeled input, select, textarea | Status label plus icon, helper, invalid, disabled, focus |
| Toast, modal and drawer | explicit Jinja macros and native dialogs | Info/success/error, focus trap, Escape, close and restore focus |
| Tabs, table, pagination and dropdown | explicit Jinja macros | Selected tab, empty table, disabled paging, expanded menu |
| KPI, chart, skeleton and empty state | explicit Jinja macros | Data summary, chart description, loading, empty |
| Avatar, stepper, command palette and nav shells | explicit Jinja macros | Initials fallback, current/completed steps, search shell, active navigation |

Error pages `/404`, `/500`, and `/offline` use the flat Obsidian and glass patterns. Missing responsive, data, and interaction states extend the nearest Figma component pattern; the component sheet is the reference for those states.

## Customer portal frame disposition

The customer frames are implemented through shared responsive templates. Their 390, 820, and 1440 px variants map to the same routes and are handled with CSS breakpoints. The only deferred customer frames are the full-day waitlist, waitlist-joined, and slot-opened states at all three widths. They need the waitlist table, endpoints, outbox flow, and acceptance rules assigned to Phase 6; see [screens.md](screens.md).

The customer and owner portals now use the implemented API endpoints. The platform-admin screens, email frame layouts, and customer waitlist frames remain deferred; see the relevant inventories and Phase 6 roadmap.

## Prototype flows to verify

- Book end to end.
- Cancel a late booking.
- Owner confirms and completes a booking.
- Owner explores analytics.
- Owner signs in and requests a password reset.
- Staff accepts an invite.
- Owner completes onboarding.
