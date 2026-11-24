# ADR 0011: Keep the frontend framework-free

- Status: Accepted
- Decision: Build the UI with Jinja, HTML, CSS, and native JavaScript modules; draw charts with hand-written SVG.
- Reason: Keep deployment and runtime dependencies small and retain direct control over accessibility and CSP.
- Consequences: Shared components use explicit Jinja macros and reusable CSS/JS modules.
