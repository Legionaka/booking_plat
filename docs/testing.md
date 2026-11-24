# Testing and quality gates

## Test layers

| Layer | Command | Proves |
| --- | --- | --- |
| Unit | `pytest -q tests/unit` | Pure service, validation, rendering, and helper behavior. |
| Contract | `pytest -q tests/contract` | Docs/routes/env/schema/repository contracts and OpenAPI drift. |
| Integration | `pytest -q tests/integration` | PostgreSQL transactions, migrations, tenant behavior, startup and adapters. Requires PostgreSQL/Redis where noted. |
| Browser | `python scripts/run_e2e.py` | Chromium user flows, responsive states, screenshots and axe checks. Requires PostgreSQL, Redis, and Chromium. |
| Full gate | `python scripts/check.py --e2e` | Locked dependencies, Ruff, frontend policy, coverage, browser suite, Render checks, Docker build. |

Start Postgres and Redis with `docker compose up -d db redis`. Browser logs/screenshots go to ignored `.artifacts/e2e`; committed product captures belong in `docs/assets/screenshots`.

## Coverage policy

The full check enforces at least 80% total application coverage and 85% for `app/services`. Do not exclude uncovered code merely to meet a threshold; add focused tests or document a genuine limitation.

## Accessibility and style

The Playwright axe suite checks public, customer, owner, staff, and component routes. Serious and critical violations fail. `scripts/check_frontend_policy.py` rejects inline styles/scripts, third-party assets, data URIs, gradients, SVG gradient paints, and mask fades.

## Results

## Latest verified run

Full gate completed on 2026-11-23 with `python scripts/check.py --e2e` on Windows, Python 3.14.3, PostgreSQL 17, Redis 7, and Chromium 159:

- Backend, integration, migration, and contract suite: **273 passed, 1 skipped** in 186.41 seconds. The skip is `tests/integration/test_bookings.py:1227`: the normal RQ worker requires Linux `fork`.
- Browser and axe suite: **108 passed, 0 failed** in 1,657.90 seconds.
- Total application coverage: **88.77%** (required 80%).
- `app/services` coverage: **89.85%** (required 85%).
- Ruff, frontend policy, gradient checks, route/docs/environment contracts, Render blueprint contract, and Docker production image build: **passed**.
- Axe: **0 serious or critical violations** across the registered rendered-page routes.

The browser suite saves committed README captures under `docs/assets/screenshots/` and local diagnostic captures under `.artifacts/e2e/`. `coverage.json` and `.artifacts/` are generated local outputs and are ignored by Git.
