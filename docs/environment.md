# Environment variables

Production startup validates every required value below before serving requests. Values shown as defaults describe `development`/test operation; use the stated secure production value instead. Put credentials in the host's secret store, never in Git.

`DATABASE_URL` may use the standard `postgres://` or `postgresql://` scheme; the application normalizes either form to `postgresql+psycopg://` for psycopg 3. Production requires a non-loopback managed PostgreSQL URL and managed Redis URLs; unset values and `localhost`, `127.0.0.1`, or `::1` endpoints are rejected with a variable-specific message.

| Variable | Required in production | Default | Purpose |
| --- | --- | --- | --- |
| `FLASK_APP` | No | `app:create_app` | Flask CLI application factory target for local commands. |
| `FLASK_DEBUG` | No | `0` | Flask development debug switch; keep disabled outside local development. |
| `APP_ENV` | Yes (`production`) | `development` | Enables production startup guards and HSTS. |
| `SECRET_KEY` | Yes, unique random value | `local-development-only` | Signs application tokens and security-related data. |
| `DATABASE_URL` | Yes | local PostgreSQL URL | PostgreSQL connection string. |
| `TEST_DATABASE_URL` | No | local test database URL | Dedicated PostgreSQL database used by the integration tests. |
| `MIGRATION_DATABASE_URL` | No | local migration test database URL | Empty PostgreSQL database used to test migration upgrade and rollback. |
| `TEST_REDIS_URL` | No | `redis://localhost:6379/15` | Isolated Redis database used by tests. |
| `POSTGRES_DB` | No | `booking_platform` | Local Docker Compose database name. |
| `POSTGRES_USER` | No | `booking` | Local Docker Compose database user. |
| `POSTGRES_PASSWORD` | No | `booking_dev_only` | Local Docker Compose database password; replace outside local development. |
| `REDIS_URL` | Yes, managed Redis URL | `redis://localhost:6379/0` | Sessions, RQ queue, and scheduler coordination. |
| `RATELIMIT_STORAGE_URI` | Yes, managed Redis URL | `redis://localhost:6379/1` | Shared Flask-Limiter storage. |
| `RATELIMIT_KEY_PREFIX` | No | `booking-platform:` | Prefix isolates rate-limit keys. |
| `EMAIL_BACKEND` | Yes (`smtp` or `http_api`) | `console` | Email delivery backend; production console delivery is refused. |
| `EMAIL_PROVIDER` | Yes when `http_api` is selected | `resend` | HTTPS email provider: `brevo`, `resend`, or `mailgun`. |
| `EMAIL_API_KEY` | Yes when `http_api` is selected | empty | Provider API key; use a sending-scoped key where the provider supports it. This is not an SMTP password/token. |
| `EMAIL_FROM_ADDRESS` | Yes when `http_api` is selected | empty | Verified sender address. |
| `EMAIL_FROM_NAME` | No | `Booking Platform` | Display name for HTTPS email providers. |
| `EMAIL_MAILGUN_DOMAIN` | Yes for Mailgun | empty | Verified Mailgun sending domain. |
| `EMAIL_MAILGUN_REGION` | No | `us` | Mailgun API region: `us` or `eu`. |
| `SMTP_HOST` | Yes when `EMAIL_BACKEND=smtp` | empty | SMTP server hostname. |
| `SMTP_PORT` | No | `587` | SMTP server port. |
| `SMTP_USERNAME` | No | empty | SMTP authentication user when required by provider. |
| `SMTP_PASSWORD` | No | empty | SMTP authentication password when required by provider. |
| `SMTP_FROM_ADDRESS` | Yes when `EMAIL_BACKEND=smtp` | empty | SMTP sender address. |
| `SMTP_TLS_MODE` | Yes when `EMAIL_BACKEND=smtp` (`starttls` or `ssl`) | `starttls` | Use SMTP STARTTLS on the configured port (typically 587) or implicit SSL (typically 465). TLS cannot be disabled in production. |
| `SMTP_TIMEOUT_SECONDS` | No | `10` | SMTP connection timeout. |
| `MIGRATE_ON_STARTUP` | No | `false` | When true, the web container applies Alembic migrations before starting Gunicorn, under a PostgreSQL advisory lock. |
| `SEED_DEMO_ON_STARTUP` | No (`false` in production) | `false` | When true, the web entrypoint runs migrations and seeds Fade Lab under the same PostgreSQL advisory lock. Requires `DEMO_MODE=true` and a non-default `DEMO_OWNER_PASSWORD` environment value. |
| `DEMO_MODE` | No | `false` | Public demo flag returned from `GET /api/config`; cannot be true while PayFast live mode is selected. |
| `SESSION_COOKIE_SECURE` | Yes (`true`) | `false` | Restricts session cookies to HTTPS; keep false only for local HTTP development. |
| `SERVER_SESSION_TTL_SECONDS` | No | `86400` | Server-side session lifetime. |
| `TRUSTED_PROXY_HOPS` | Yes, set explicitly to host's exact proxy hop count | `0` | Trust forwarded client IP/protocol/host headers only from configured proxies. Zero means ignore all forwarded headers. |
| `WEB_WORKERS` | No | `3` | Gunicorn worker process count. |
| `PORT` | No | `5000` | Web listener port, commonly supplied by the host. |
| `LOG_LEVEL` | No | `INFO` | Application log threshold. Logs are structured JSON and omit request bodies and credentials. |
| `SENTRY_DSN` | No | empty | Enables Sentry only when set; request PII is scrubbed. |
| `AUTH_REGISTER_RATE_LIMIT` | No | `20 per hour` | Registration attempts per IP. |
| `AUTH_LOGIN_EMAIL_RATE_LIMIT` | No | `5 per minute` | Login attempts by IP and email. |
| `AUTH_LOGIN_IP_RATE_LIMIT` | No | `30 per hour` | Login attempts by IP. |
| `AUTH_FORGOT_EMAIL_RATE_LIMIT` | No | `5 per hour` | Password reset requests by IP and email. |
| `AUTH_FORGOT_IP_RATE_LIMIT` | No | `30 per hour` | Password reset requests by IP. |
| `AUTH_RESET_TOKEN_RATE_LIMIT` | No | `5 per hour` | Password reset submissions by token. |
| `AUTH_RESET_IP_RATE_LIMIT` | No | `30 per hour` | Password reset submissions by IP. |
| `AUTH_RESEND_VERIFICATION_EMAIL_RATE_LIMIT` | No | `3 per hour` | Verification resend attempts by IP and email. |
| `AUTH_RESEND_VERIFICATION_IP_RATE_LIMIT` | No | `30 per hour` | Verification resend attempts by IP. |
| `AUTH_RESEND_VERIFICATION_COOLDOWN_SECONDS` | No | `60` | Minimum wait between verification emails. |
| `PUBLIC_AVAILABILITY_RATE_LIMIT` | No | `60 per minute` | Public availability requests. |
| `AVAILABILITY_MINIMUM_NOTICE_MINUTES` | No | `120` | Minimum booking notice. |
| `AVAILABILITY_MAXIMUM_ADVANCE_DAYS` | No | `60` | Maximum booking advance window. |
| `HOLD_MINUTES` | No | `15` | Pending booking hold lifetime. |
| `MAX_PENDING_HOLDS_PER_USER` | No | `3` | Maximum active pending holds per customer. |
| `BOOKING_CREATE_RATE_LIMIT` | No | `10 per minute` | Booking creation request limit. |
| `RQ_QUEUE_NAME` | No | `default` | RQ queue consumed by the worker. |
| `NOTIFICATION_BATCH_SIZE` | No | `100` | Due outbox notifications enqueued per scheduler pass. |
| `SCHEDULER_INTERVAL_SECONDS` | No | `60` | Scheduler polling interval. |
| `NOTIFICATION_IN_PROGRESS_TIMEOUT_SECONDS` | No | `300` | Recovery timeout for stuck notification jobs. |
| `NOTIFICATION_RETRY_INTERVALS_SECONDS` | No | `60,300,900,900` | Delays between retries, up to five total attempts. |
| `BOOKING_MANAGE_BASE_URL` | Yes, HTTPS origin | `http://localhost:5000` | Base link used in booking notification emails. |
| `PAYFAST_MERCHANT_ID` | Yes | empty | PayFast merchant ID. |
| `PAYFAST_MERCHANT_KEY` | Yes | empty | PayFast merchant key. |
| `PAYFAST_PASSPHRASE` | Yes | empty | PayFast signature passphrase. |
| `PAYFAST_SANDBOX` | Yes (`false`) | `true` | Select PayFast sandbox or live endpoints. |
| `PAYFAST_ITN_RATE_LIMIT` | No | `600 per minute` | Configured ITN rate limit; the ITN endpoint is exempt to allow provider retries. |
| `PAYFAST_VALIDATE_TIMEOUT_SECONDS` | No | `8` | Timeout for PayFast ITN server validation. |
| `PAYMENT_HOLD_MINUTES` | No | `20` | Payment hold extension. |
| `PUBLIC_BASE_URL` | Yes, HTTPS origin | `http://localhost:5000` | Public origin used to construct PayFast callback URLs. |
| `DEMO_OWNER_EMAIL` | No | `owner@fade-lab.demo` | Local demo seed owner login. |
| `DEMO_OWNER_PASSWORD` | Yes, unique environment secret | `DemoOnly-ChangeMe-2026!` (local only) | Demo owner password. Production rejects the repository default. Startup seeding also requires an explicit non-default value. |
| `DEMO_OWNER_NAME` | No | `Fade Lab Owner` | Local demo seed owner display name. |

Production also requires a non-default `SECRET_KEY`, an SMTP backend with TLS, HTTPS public URLs, a non-sandbox PayFast configuration, and an explicitly configured `TRUSTED_PROXY_HOPS` greater than zero. Set that value to the exact number of trusted reverse proxy hops for the selected host. If it is too high, a client may spoof `X-Forwarded-For`; that can undermine IP-based rate limits and client-IP logging. If it is too low, rate limits may key on the proxy address and affect multiple users together. Zero ignores forwarded headers and is the safe local default, but production startup rejects it. `SENTRY_DSN` and SMTP authentication credentials are optional; configure both SMTP credentials or neither.

Keep `SEED_DEMO_ON_STARTUP=false` in production. If using startup seeding in a demo environment, set both `SEED_DEMO_ON_STARTUP=true` and `DEMO_MODE=true`, and supply a unique `DEMO_OWNER_PASSWORD` through the hosting environment's secret store. The web entrypoint will refuse to start if the flags disagree or the repository's demo password is still configured.

The local browser test runner accepts `E2E_PORT` (default `5001`), `E2E_SMOKE_ONLY` and `E2E_LAYOUT_ONLY` (both default `false`), `E2E_TEST_PATHS` (optional path-separated pytest paths), `E2E_BASE_URL` (default `http://127.0.0.1:5001`), `E2E_EMAIL_LOG` (the runner-managed server log path), and `AUTH_LAYOUT_SCREENSHOT_DIR` (default `.artifacts/e2e/auth-layout`). These optional settings are not needed by the deployed application.
