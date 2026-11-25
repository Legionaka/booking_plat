# Accessibility notes

The UI uses semantic HTML, visible keyboard focus, labeled inputs, accessible names for chart SVG, keyboard-operable dialogs, Escape handling, focus restoration, and reduced-motion preferences. Touch targets are designed for at least 44 CSS pixels. Chart empty states do not invent values.

The public landing page has a skip link, one h1, a keyboard-operable slot picker with aria-pressed states, and a mobile menu that traps focus and closes with Escape. Landing interactions and hover presses respect reduced motion.

Playwright axe tests fail on serious and critical violations across supported routes. Run them with `python scripts/run_e2e.py`. Automated checks do not replace keyboard and screen-reader review; check login, booking selection, dialogs/drawers, responsive navigation, and error/empty states manually.
