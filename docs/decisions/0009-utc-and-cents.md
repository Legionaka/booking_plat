# ADR 0009: Store UTC instants and integer cents

- Status: Accepted
- Decision: Persist timestamps as UTC-aware values, interpret schedules in each business timezone, and store money as integer cents.
- Reason: This avoids timezone ambiguity and floating-point currency arithmetic.
- Consequences: Convert at UI/API edges and snapshot prices on bookings.
