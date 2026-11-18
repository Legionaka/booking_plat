# Operations

## Release and migrations

Build and deploy one immutable image to web, worker, and scheduler. Before the new web version receives traffic, run the release command:

```sh
flask --app app:create_app db upgrade
```

Render runs this as its web service `preDeployCommand`. Do not start the new version if the migration command fails. The PostgreSQL migration integration test applies the migration to an empty dedicated database, checks the tables and indexes, rolls it back, then upgrades it again:

```sh
pytest -q tests/integration/test_migration.py
```

For a lower-cost host without a separate release phase, set `MIGRATE_ON_STARTUP=true` on the web container. Its entrypoint runs `flask db upgrade` before Gunicorn while holding a PostgreSQL session advisory lock, so only one concurrent startup migrates at a time. This is off by default. Keep it off when the host already runs the release command above.

For a demo environment that should populate itself at each deployment, set `SEED_DEMO_ON_STARTUP=true` and `DEMO_MODE=true`. The web entrypoint acquires a PostgreSQL advisory lock, runs `flask db upgrade`, and then invokes the explicit `flask seed-demo` command as a separate step while still holding the lock. This happens even when `MIGRATE_ON_STARTUP=false`. Alembic and ordinary Flask CLI commands never seed data; `flask db upgrade`, `flask db check`, and `flask routes` remain safe to run against a new database. Other web instances wait for the lock before migrating or seeding. The seed is idempotent, so a restart reuses Fade Lab records without duplicating them. If migration or seeding fails, the web process exits nonzero and Gunicorn does not start. The seed flag alone is rejected.

Set `DEMO_OWNER_PASSWORD` explicitly in the host's environment/secret store before enabling startup seeding. Do not use the repository's local demo password in production; keep `SEED_DEMO_ON_STARTUP=false` there. Production startup rejects the repository default, and the demo seed is intended for sandbox/demo environments only.

## Dependency updates and local verification

`requirements.in` and `requirements-dev.in` contain supported version ranges. `requirements.txt` and `requirements-dev.txt` are the pip-tools compiled locks with hashes; the production Docker build and CI install from those lock files with `--require-hashes`. The supported Pydantic range is `>=2,<3`. The checked-in resolver output currently selects Pydantic 2.14.3, and compilation with that broader range resolves successfully. No package conflict is reproducible from the current inputs, so there is no conflicting package to name; preserve any resolver error output if a future range change fails rather than narrowing the range speculatively.

To update dependencies, edit only the applicable `.in` range file, then compile both lock files with the development toolchain:

```sh
python -m pip install pip-tools
python -m piptools compile --upgrade --allow-unsafe --strip-extras --generate-hashes --output-file=requirements.txt requirements.in
python -m piptools compile --upgrade --allow-unsafe --strip-extras --generate-hashes --output-file=requirements-dev.txt requirements-dev.in
```

Review the pins and hashes, then run `python scripts/check.py`. Dependabot opens weekly PRs for pip, GitHub Actions, and Docker updates. CI and local verification use the same script so lint, frontend policy, the full test suite, and the production image build stay in sync.

For a local run, start real Postgres and Redis first with `docker compose up -d db redis`, then run `python scripts/check.py`. It installs the hashed development lock, creates the two dedicated test databases if needed, runs Ruff and the frontend policy scanner, runs the full pytest suite, and builds the production Docker image. CI provides Postgres and Redis service containers and invokes the same command.

## Render deployment setup

Create a Render Blueprint from `render.yaml`. The web service's `preDeployCommand` applies migrations before the new web process starts; Render requires a paid compute plan for pre-deploy commands. The Blueprint uses a Frankfurt web service, background worker, scheduler, managed PostgreSQL database, and managed Key Value (Redis) service. See [Render's Blueprint reference](https://render.com/docs/blueprint-spec) for current resource fields and plan choices.

Fill the secret placeholders in the `booking-platform-production` environment group: SMTP host/from address (and credentials if required), the public HTTPS app URL for both URL settings, and live PayFast merchant ID/key/passphrase. Render generates `SECRET_KEY`. Add `SENTRY_DSN` only if you have a Sentry project. Set the `TRUSTED_PROXY_HOPS` value to the actual proxy count for the chosen host. Attach a custom domain in Render and update its DNS records at your registrar; replace the README CI badge's `OWNER/REPOSITORY` with the GitHub repository path. Do not commit these values.

## PostgreSQL backup and restore

Use the managed database's scheduled backups and retain a separate encrypted export for recovery. For a manual logical backup from an operator machine with `pg_dump` installed:

```sh
pg_dump --format=custom --no-owner --file=booking-platform.dump "$DATABASE_URL"
```

Restore into a new or explicitly approved empty recovery database first, then verify the application before changing the production connection string:

```sh
createdb booking_platform_restore
pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" booking-platform.dump
```

Never restore over production without a reviewed recovery plan. Preserve and protect the dump as sensitive data; it contains customer and payment records.

## Demo data on staging

Confirm the environment is staging, use a dedicated demo owner password, then run:

```sh
flask --app app:create_app seed-demo
```

To recreate only the Fade Lab demo business and its related records:

```sh
flask --app app:create_app seed-demo --reset
```

The command refuses `APP_ENV=production`. Demo credentials are not suitable for production or shared staging; set `DEMO_OWNER_EMAIL`, `DEMO_OWNER_PASSWORD`, and `DEMO_OWNER_NAME` before use.

## Secret rotation

Rotate `SECRET_KEY` during a planned maintenance window; this invalidates signed verification/reset tokens. Rotate Redis/PostgreSQL credentials at the provider, update the host's secret store and dependent service references together, then redeploy web, worker, and scheduler. Rotate SMTP and PayFast credentials in their provider dashboards before updating `SMTP_PASSWORD` or the `PAYFAST_*` values. Do not print secrets in shell history, logs, or tickets. Recheck `/ready` and send a test email/payment after rotation.

## Workers and scheduler

The Docker Compose services use the same image and separate commands. Locally:

```sh
docker compose up --build db redis web worker scheduler
```

For a manual process, run `flask --app app:create_app worker run` and `flask --app app:create_app scheduler run` in separate terminals. Keep one scheduler process active; duplicate passes are safe, but a single scheduler is operationally simpler. Monitor JSON logs for retry failures and inspect notification status in PostgreSQL.

For a small demo where a host charges per service, run the web server, RQ worker, and scheduler under one supervisor/container:

```sh
flask --app app:create_app demo run-all
```

This starts Gunicorn, the normal RQ worker, and the scheduler as child processes. The supervisor exits nonzero and stops the other services if any child exits, so the host can restart the container. Separate processes keep RQ signal handling on the worker's main thread. It is for low-traffic demos, not production scaling. Provide the same database, Redis, email, and PayFast sandbox settings used by the separate services. Set `DEMO_MODE=true` to let a frontend display its no-real-payments banner; startup refuses that mode if `PAYFAST_SANDBOX=false`.

## Health and incidents

Use `/health` for liveness and `/ready` for PostgreSQL/Redis readiness. Each response includes `X-Request-ID`; use that ID to correlate application JSON logs. Keep raw PayFast ITN payload retention limited as described in `payments.md`.
