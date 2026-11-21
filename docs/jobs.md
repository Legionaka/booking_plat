# Background jobs and notifications

Booking confirmation and reminder intents are inserted into `notifications` in the same transaction as booking creation or confirmation. The unique `(booking_id, kind)` key makes these inserts retry-safe. Confirmation is scheduled immediately. The 24-hour and 2-hour reminders are omitted when their scheduled time has already passed.

Cancelling, completing, or marking a booking no-show cancels its unsent notifications. A cancellation by a business user or the system also queues a cancellation email; a customer cancelling their own booking does not email them about their own action. Rescheduling updates the scheduled times on unsent reminders.

## Run locally

Start PostgreSQL and Redis, then run these in separate terminals:

```powershell
flask --app app:create_app worker run
flask --app app:create_app scheduler run
```

The scheduler polls every `SCHEDULER_INTERVAL_SECONDS` (60 seconds by default), enqueues due rows in batches of `NOTIFICATION_BATCH_SIZE`, and expires booking holds. It recovers queued or retrying rows if their Redis job disappeared, and re-enqueues jobs whose worker heartbeat has been stale for `NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS` (300 seconds by default). Job IDs use the stable form `notification-<id>`, so repeated passes do not stack jobs. Run the same services with Docker Compose using `docker compose up --build web worker scheduler`.

Retryable email delivery failures (timeouts, connection errors, HTTP 429, and HTTP 5xx) are retried up to five total attempts, with delays from `NOTIFICATION_RETRY_INTERVALS_SECONDS` (60, 300, 900, and 900 seconds by default). Permanent HTTP errors such as 401, 403, and other 4xx responses immediately mark the outbox row `failed` and do not retry. A row that exhausts retries also becomes `failed`; successful delivery sets `sent_at` and status `sent`. Delivery is **at-least-once**: if a worker crashes after the provider accepts an email but before the database commit, a retry can send it again. The database row lock prevents concurrent workers from sending the same outbox row at the same time. Email rendering provides plain text and simple HTML, with business-local date, time, and timezone name. `BOOKING_MANAGE_BASE_URL` supplies the base of the booking management link.
