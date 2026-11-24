# ADR 0007: Enforce booking overlap in PostgreSQL

- Status: Accepted
- Decision: Use a partial GiST exclusion constraint over staff and the occupied time range for pending and confirmed bookings.
- Reason: Concurrent requests can pass an application-level availability check at the same time.
- Consequences: PostgreSQL is the concurrency authority; service code translates exclusion violations into 409. Buffers are included through `blocked_until`.
