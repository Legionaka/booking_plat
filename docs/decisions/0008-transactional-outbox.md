# ADR 0008: Deliver notifications through a transactional outbox

- Status: Accepted
- Decision: Commit notification intent with booking/payment changes and deliver it asynchronously through RQ.
- Reason: Sending before transaction commit can announce rolled-back state; sending after commit without durable intent can lose mail on process failure.
- Consequences: Jobs must be idempotent, retryable errors are bounded, and permanent failures remain inspectable.
