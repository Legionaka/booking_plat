# AGENTS.md

## Project
Multi-tenant booking platform for small businesses (barbers, clinics, tutors).
Stack: Flask, PostgreSQL, Redis with RQ, vanilla HTML/CSS/JS frontend.
Planning doc: docs/planning.md

## Sources of truth
- Visual design: the Figma file at <https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=0-1>. Figma wins on how things look.
- Frame-to-route map: docs/design/figma.md
- Behavior, data and rules: the planning doc, docs/schema.sql and docs/api.md.

## Backend rules
- Python, Flask blueprints, SQLAlchemy, Alembic migrations, Pydantic validation.
- Keep routes thin. Business logic lives in app/services.
- Store all times in UTC. Store money as integer cents.
- Scope every tenant-owned query by business_id.
- Double-booking is prevented by the database exclusion constraint. Catch the error and return 409.
- Webhooks and jobs must be idempotent.

## Frontend rules
- Vanilla HTML, CSS and JS only. No frameworks, no Tailwind, no chart library.
- Charts are hand-written SVG in static/js/charts.
- All colors, radii, blur and fonts come from static/css/tokens.css. Never hard-code them.
- Theme: dark, black, glassy, silver. Monochrome. Amber, Jade and Rose are for booking status only. No purple.
- Every glass surface needs a solid fallback. Respect prefers-reduced-motion. Keep focus rings visible and tap targets at least 44 px.
- Pointer-following sheen and cursor-driven `--mx`/`--my` lighting are removed from glass, buttons, and slot keys. Keep the slowly drifting ambient background light and ordinary hover/press states.
- Match Figma spacing, radii and states. If a state is missing in Figma, extend the nearest pattern and note it in docs/design/figma.md.
- Shared template components are Jinja macros with explicit arguments and defaults. Never rely on variables inherited from the calling template; keep component inputs explicit so one component cannot change another through leaked template state.
- No inline `<style>` blocks, style attributes, `setAttribute('style', ...)`, or inline event handlers. Use CSS classes, CSS files, external scripts, and `element.style.setProperty` only for dynamic values.
- Do not use `data:` URIs for images or CSS backgrounds. SVG charts get their styling from CSS classes. Render QR codes as SVG DOM elements or serve them from an application-owned endpoint.
- Run `python scripts/check_frontend_policy.py` before finishing frontend changes. CI runs this scanner and fails on inline styles, inline scripts, event handlers, or `data:` URIs in templates and static files.
- No inline `<style>` blocks, style attributes, `setAttribute('style', ...)`, or inline event handlers. Use CSS classes, CSS files, external scripts, and `element.style.setProperty` only for dynamic values.
- Do not use `data:` URIs for images or CSS backgrounds. SVG charts get their styling from CSS classes. Render QR codes as SVG DOM elements or serve them from an application-owned endpoint.
- Fonts must be self-hosted from `static/fonts`; frontend assets must not load from third-party hosts.
- Run `python scripts/check_frontend_policy.py` before finishing frontend changes. CI runs this scanner and fails on inline styles, inline scripts, event handlers, or `data:` URIs in templates and static files.

## Workflow
- Follow the build order in the planning doc (backend phases and frontend order).
- Work on one feature at a time and write tests with it.
- Run pytest and ruff before finishing a task.
- Ask before adding a dependency or changing the schema. Schema changes need a migration.

## Never
- Commit secrets. Use environment variables and keep .env.example current.
- Skip input validation or role checks.
- Introduce colors outside the palette.
