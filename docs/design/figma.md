# Figma handoff

## Source of truth

- Figma is the source of truth for visual design. The product plan is the source of truth for behavior, data, and business rules.
- Project Figma file: [Booking platform design](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=0-1) (link currently recorded in `AGENTS.md`).
- The planning document still contains placeholder page names. Confirm the page and frame names against Figma before implementing a screen; do not infer missing visual details from the placeholders.
- If Figma and the product plan differ visually, follow Figma. If they differ on behavior, follow the product plan and record the discrepancy here.

## Figma organization

The plan asks for frames named `Portal / Screen / State`, with colors, type, radius, and blur represented as Figma variables. The following page names and frame IDs need to be filled in after inspecting the file:

| Area | Figma page/frame | Status |
| --- | --- | --- |
| Design system: tokens, glass depths, slot states, components, chart styles | TBD | Verify in Figma |
| Customer portal | TBD | Verify in Figma |
| Owner and staff portal | TBD | Verify in Figma |
| Platform admin | TBD | Verify in Figma |
| Authentication and onboarding | TBD | Verify in Figma |
| System states and emails | TBD | Verify in Figma |

## Screen-to-route map

This map follows the product plan's screen inventory. Exact frame names, node links, dimensions, and state coverage remain to be checked against Figma.

| Area | Route(s) | Template group | Main API calls |
| --- | --- | --- | --- |
| Customer booking | `/b/<slug>`, `/b/<slug>/book`, `/b/<slug>/book/time`, `/b/<slug>/book/pay`, `/b/<slug>/book/confirmed/<id>`, `/b/<slug>/waitlist` | `customer/` | Public services, availability slots, booking creation, payments |
| Customer account | `/account/bookings`, `/account/bookings/<id>`, `/account/security` | `customer/`, `auth/` | Customer bookings, booking updates, sessions |
| Authentication | `/auth/login`, `/auth/register`, `/auth/verify`, `/auth/forgot`, `/auth/reset/<token>`, `/auth/invite/<token>`, `/auth/2fa` | `auth/` | Authentication endpoints |
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
| `color/glass-fill`, `color/glass-border`, `color/glass-top` | `--glass`, `--glass-border`, `--glass-top` |
| `color/pearl`, `color/silver`, `color/fog`, `color/dim`, `color/steel` | `--pearl`, `--silver`, `--fog`, `--dim`, `--steel` |
| `color/amber`, `color/jade`, `color/rose` | `--amber`, `--jade`, `--rose` |
| `radius/panel`, `radius/card`, `radius/control`, `radius/slot` | `--r-panel`, `--r-card`, `--r-control`, `--r-slot` |
| `type/display`, `type/ui` | `--font-display`, `--font-ui` |
| `blur/glass` | `--blur-glass` |

The plan's starting theme is Obsidian `#050506`, Graphite `#0E0F12`, Pearl `#F5F6F8`, Silver `#C4C9D4`, Fog `#9298A6`, Dim `#7A8090`, Steel `#8A93A6`, Amber `#E3B25C`, Jade `#4ADE9F`, and Rose `#FF6B8A`. Amber, Jade, and Rose are reserved for booking status. Confirm final values and spacing tokens against Figma.

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

The availability engine and booking endpoints should exist before the customer booking and owner dashboard screens are connected to real data. Until then, use fixture JSON matching `docs/api.md`.

## Prototype flows to verify

- Book end to end.
- Cancel a late booking.
- Owner confirms and completes a booking.
- Owner explores analytics.
- Owner signs in and requests a password reset.
- Staff accepts an invite.
- Owner completes onboarding.
