# Contributing

## Setup

1. Install Docker Compose and Python 3.12+.
2. Copy `.env.example` to `.env` and set local values.
3. Start local services with `docker compose up -d db redis` (or `docker compose --profile dev up` for Mailpit).
4. Install hash-locked development dependencies: `python -m pip install --require-hashes -r requirements-dev.txt`.
5. Apply migrations and seed if desired: `flask --app app:create_app db upgrade` and `flask --app app:create_app seed-demo`.

## Checks

Run `python scripts/check.py --e2e` before proposing changes when Docker, PostgreSQL, Redis, and Chromium are available. See [docs/testing.md](docs/testing.md) for individual layers. Never report a check as passing unless it ran on the current tree.

## Change conventions

- Keep business rules in services and add focused tests with behavior changes.
- Include Alembic migrations for approved schema changes; do not alter existing tables without approval.
- Keep `.env.example`, environment docs, OpenAPI, and route documentation in sync.
- Use concise commit subjects such as `phase 5: add testing and security docs`.
- Do not commit credentials, `.env`, local databases, logs, or `.artifacts`.
