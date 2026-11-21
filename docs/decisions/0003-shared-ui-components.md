# ADR 0003: shared UI components

## Decision

Use explicit-argument Jinja macros for reusable component markup, CSS component files for presentation, and external JavaScript modules for interactions. The component sheet at `/dev/components` is the rendered reference for shared UI states. Native HTML dialogs provide modal semantics, with explicit keyboard focus trapping, Escape handling, and focus restoration.

## Rationale

This follows the project's vanilla frontend and strict CSP constraints, keeps component inputs isolated from caller template state, and lets the browser provide built-in dialog behavior. Missing Figma states extend the closest documented pattern. Figma's ambient light and visual highlights remain omitted under the global flat-style rule.

## Consequences

The component accessibility suite uses the dev-only `axe-playwright-python` integration. The CSS remains usable when backdrop blur is unsupported because each surface has a solid Graphite fallback.
