# AGENTS.md

## Project
Multi-tenant booking platform for appointment-based businesses. Python 3.12+, Flask, PostgreSQL, Redis/RQ, SQLAlchemy, Alembic, Pydantic, and vanilla HTML/CSS/JS. The shipped feature set and deferred work are in [docs/planning.md](docs/planning.md).

## Sources of truth
- Visual design: [Figma](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=0-1); recorded mapping and overrides: `docs/design/figma.md` and `docs/design/screens.md`.
- Behavior/API: `docs/api.md`; data reference: `docs/schema.sql`; current architecture: `docs/architecture.md`.

## Backend rules
- Use Flask blueprints, SQLAlchemy, Alembic migrations, and Pydantic validation.
- Keep routes thin; business logic belongs in `app/services`.
- Store instants in UTC and money as integer cents.
- Scope every tenant-owned query by `business_id`; enforce roles on every protected operation.
- PostgreSQL exclusion constraint prevents double-booking; translate conflicts to HTTP 409.
- Webhooks and background jobs must be idempotent. Notification intent goes through the transactional outbox.
- Never change an existing database table or column without explicit approval. New tables require Alembic migrations.

## Frontend rules
- Vanilla HTML, CSS, and JavaScript only; no frameworks or charting libraries. Charts are hand-written SVG in `app/static/js/charts`.
- Use design tokens from `app/static/css/tokens.css`; do not introduce colors outside the palette.
- Dark monochrome flat surfaces: no gradients, gradient SVG paints, masks/fades, gradient text, ambient light layer, or pointer sheen. Status colors are reserved for booking status.
- Glass surfaces need a solid fallback and 1 px border. Respect reduced motion, visible focus, and 44 px minimum touch targets.
- Jinja component macros take explicit arguments and defaults; never depend on caller context.
- No inline styles/scripts/handlers, `data:` URIs, external assets, or third-party fonts. Fonts are self-hosted.
- Before finishing frontend work run `python scripts/check_frontend_policy.py` and the browser accessibility tests.

## Workflow
- Follow [docs/planning.md](docs/planning.md) and the phase/build order.
- Add tests with feature work. Run `python scripts/check.py --e2e` before phase completion when PostgreSQL, Redis, and Chromium are available. Report blockers and actual counts.
- Run Ruff and preserve hash locks for dependency changes. Pre-approved packages are listed in the master task: `pytest-cov`, `pyotp`, `segno`, and axe integration for Playwright.
- Keep `.env.example` and `docs/environment.md` aligned. Never commit secrets, local databases, logs, or generated test artifacts.
