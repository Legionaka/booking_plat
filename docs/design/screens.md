# Screen map

Figma source: [Booking platform design](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=2-479). Customer frame inventory was read from `Customer • Book in a minute` (`2:479`) and `Customer • Desktop and tablet` (`2:3463`). Desktop/tablet/mobile variants share the routes below; responsive CSS switches the layout at 760 px. The product flat-style override removes ambient lighting, pointer effects, glows, gradients, and decorative fades from each frame.

| Customer state | Figma frame IDs | Route and implementation | Data and states |
|---|---|---|---|
| Business landing | 390: `2:480`; 820: `2:3502`; 1440: `2:3464` | `/b/{slug}` · `customer/portal.html`, `customer.js` | `GET /api/config`, business, services, availability range, then first open slot; loading, no services, API error, offline |
| Choose service and staff | 390: `2:512`; 820: `2:3574`; 1440: `2:3534` | `/b/{slug}/book` | Public services and staff; selected service, staff, disabled/ready continue states |
| Choose date and time | 390: `2:546`; 820: `2:3655`; 1440: `2:3608` | `/b/{slug}/book/time` | Range availability and daily slots; selected Pearl slot with 2 px ring, empty day, invalid service, conflict refresh |
| Time selected / deposit review | 390: `2:599`, `2:638`; 820: `2:3729`, `2:3792`; 1440: `2:3696`, `2:3756` | `/b/{slug}/book/review` | Service/staff detail, local time, price and deposit; `POST /api/b/{slug}/bookings` |
| Hosted payment handoff | 390: `2:668`; 820: `2:3859`; 1440: `2:3822` | `POST /payments/handoff/{id}` | Server signs fields; route-specific PayFast form-action CSP only |
| Payment pending | 390: `2:699`; 820: `2:3917`; 1440: `2:3890` | `/payments/return?booking_id={id}` | Polls `GET /api/me/bookings/{id}` for ITN-set payment and booking status; browser return never confirms |
| Booking confirmed | 390: `2:720`; 820: `2:3969`; 1440: `2:3938` | `/b/{slug}/book/confirmed/{id}` | Owned booking detail; confirmed or pending copy from server state |
| My bookings | 390: `2:745`; 820: `2:4026`; 1440: `2:3994` | `/account/bookings` | `GET /api/me/bookings?filter=upcoming|past`; loading, empty, error, offline, list |
| Booking detail | 390: `2:771`; 820: `2:4083`; 1440: `2:4052` | `/account/bookings/{id}` | Owned booking detail, status, service/staff/business names, cancel/reschedule links |
| Late cancellation | 390: `2:796`; 820: `2:4133`; 1440: `2:4108` | `/account/bookings/{id}/cancel` | API `403 late_cancellation` exposes contact-business guidance; does not change booking |
| Reschedule and success | 390: `2:815`, `2:834`; 820: `2:4177`, `2:4215`; 1440: `2:4152`, `2:4196` | `/account/bookings/{id}/reschedule`, `/rescheduled` | Availability slots and `PATCH /api/bookings/{id}`; success follows server response |
| Eligible cancel and cancelled | 390: `2:987`, `2:1002`; 820: `2:4577`, `2:4610`; 1440: `2:4556`, `2:4592` | `/account/bookings/{id}/cancel`, `/cancelled` | `PATCH /api/bookings/{id}`; cutoff errors show late state; cancellation success follows API response |
| Register, login, verify, reset | 390: `2:896`, `2:918`, `2:939`, `2:954`, `2:969`; 820: `2:4372`, `2:4421`, `2:4463`, `2:4499`, `2:4538`; 1440: `2:4344`, `2:4394`, `2:4442`, `2:4478`, `2:4514` | Existing `/auth/register`, `/auth/login`, `/auth/verify`, `/auth/forgot`, `/auth/reset` | Existing auth API and validation; shared responsive auth templates |
| Waitlist full day, joined, slot opened | 390: `2:847`, `2:868`, `2:881`; 820: `2:4255`, `2:4295`, `2:4329`; 1440: `2:4228`, `2:4276`, `2:4308` | Deferred | Waitlist backend and outbox flow are assigned to Phase 6; no unsupported mock UI is presented as functional |

All signed-in customer API calls pass through the shared fetch wrapper. A 401 opens the session-expired dialog and preserves a same-origin return path; 409 `slot_taken` offers a return to availability; 422, 429, 503, and network failures display inline guidance. Demo mode is read from `GET /api/config` and deposit copy states that demo payments are sandbox only.

## Owner and staff portal frames

Figma page inventories: `Owner • Live control room` (`2:1014`) and `Responsive • Owner and system states` (`2:4670`). The desktop page includes 1440 px frames; the responsive page includes 820 px and 390 px versions. All business pages use the shared `/app/{business_id}/{section}` shell, CSS breakpoints, and tenant-scoped APIs. The separate reduced-motion dashboard frame maps to the overview with system motion disabled. The flat-style override listed above applies to every owner frame.

| Owner or staff frame | Figma IDs (desktop; tablet; mobile) | Route / implementation | APIs and states |
|---|---|---|---|
| Overview dashboard | `2:1015`, reduced motion `2:7225`; `2:4671`; `2:7532` | `/app/{business_id}/dashboard` | Analytics summary, timeseries, status mix, utilisation, current day calendar; loading/error/offline/empty and live current-time line |
| Week view | `2:1347`; `2:4961`; `2:7794` | `/app/{business_id}/week` | Calendar/week and five-step booking density; previous/next week, no staff and no bookings states |
| Payments | `2:1550`; `2:5143`; `2:7959` | `/app/{business_id}/payments` | Payments list, completed-revenue timeseries, status filter, paid-after-cancellation flag |
| Services catalogue and editor | `2:1647`, editor `2:1788`, create `2:8957`; `2:5221`, editor `2:5273`; `2:8020`, editor `2:8054` | `/app/{business_id}/services`; dialog forms | Scoped list/create/edit/deactivate APIs; server-confirmed affected-booking warning; inactive and empty states |
| Staff and editor | `2:1934`, editor `2:2064`; `2:5322`, editor `2:5365`; `2:8085`, editor `2:8110` | `/app/{business_id}/staff` | Scoped staff CRUD, service assignment checkboxes, deactivation affected-booking warning |
| Working hours and time off | `2:2200`; `2:5406`; `2:8133` | `/app/{business_id}/hours` | Read/replace weekly windows, add/remove time off, empty schedules |
| Customers and history | `2:2379`; `2:5466`; `2:8175` | `/app/{business_id}/customers` | Search, booking/no-show counts, scoped customer detail history |
| Analytics | `2:1157`; `2:4790`; `2:7635` | `/app/{business_id}/analytics` | Summary and previous-period values, bookings and revenue timeseries, outcomes, status mix, weekday/hour heatmap, staff utilisation; date range and no-data states |
| Settings and QR code | `2:2521`; `2:5523`; `2:8214` | `/app/{business_id}/settings` | Business profile/rules PATCH and protected `/app/{business_id}/qr.svg` generated with segno |
| Audit log | `2:2668`; `2:5571`; `2:8244` | `/app/{business_id}/audit` | Tenant-scoped audit API; safe change diffs and empty state |
| Bookings and status drawer | `2:2806`, pending `2:2940`, confirmed `2:2961`, completed `2:2982`; `2:5626`; `2:8281` | `/app/{business_id}/bookings` and native booking detail dialog | Calendar/list API, confirm, complete, no-show actions; status-specific actions |
| Command palette | `2:3031`; shared responsive shell | Native dialog on all owner pages | Search and navigate to available workspace sections; keyboard Escape/return focus |
| Date range popover | `2:8938`; responsive analytics filters | `/app/{business_id}/analytics` | Native date inputs and previous-period comparison |
| Walk-in booking modal | `2:3003` | Deferred | Current booking creation requires a registered customer id. Supporting anonymous walk-ins would change the existing booking/customer relationship, so no partial UI or schema change was introduced; see ADR 0005. |

Onboarding is implemented at `/app/onboarding` using existing business, service, staff, assignment, and working-hours APIs. It has four steps: business details, first service, staff and hours, and share link. There is no separate owner onboarding frame on the Owner page; this workflow extends the existing authentication/onboarding visual pattern. Staff membership navigation shows only overview, week, and bookings; the backend scopes calendar results to the staff member's own column and rejects owner-only APIs.

SVG charts are hand-written in `static/js/charts/`, use solid palette strokes, and expose an accessible name. Empty datasets render without fabricated values. Ambient fields, gradients, colored glows, and decorative fades in the source Figma owner frames are omitted under the project flat-style rule.
