# ADR 0004: responsive customer booking flow

## Decision

Use shared server-rendered Jinja page shells for the customer booking, payment-return, and account routes. Load business, availability, booking, and payment state from the existing JSON APIs through the vanilla JavaScript fetch wrapper. Reuse the same content at Figma's 390, 820, and 1440 px widths with responsive CSS.

## Rationale

The API and booking rules already exist, so the customer UI can stay thin and use the server as the source of truth. A payment return only polls the booking API; it never confirms a booking. The PayFast handoff needs an HTML POST, so the synchronizer token is accepted as a form field only on that route, in addition to the usual header token.

## Consequences

The three waitlist screens remain deferred until the Phase 6 waitlist table and notification workflow exist. Customer booking pages expose loading, empty, API error, rate-limit, offline, session-expired, conflict, and success feedback without client-side booking state transitions. The demo seed leaves one future deposit slot open each weekday so the PayFast sandbox path can be exercised.
