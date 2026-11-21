# ADR 0005: defer walk-in booking

## Status

Accepted for Phase 4.

## Context

The Figma owner page includes a walk-in booking modal. Booking creation currently requires a registered customer user and `bookings.customer_id` is non-nullable. A safe guest or walk-in flow would need new customer identity semantics and a schema/API change.

## Decision

Do not add a walk-in booking form in Phase 4. The owner action explains the limitation and links to the bookings page. Keep the existing booking and customer relationship unchanged.

## Consequences

The walk-in Figma frame (`2:3003`) is explicitly deferred. Revisit alongside a planned customer identity design and migration, with tests for customer history, notifications, and access controls.
