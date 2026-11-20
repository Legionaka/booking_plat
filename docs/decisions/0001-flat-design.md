# ADR 0001: Flat monochrome product surfaces

- Status: accepted
- Date: 2026-11-21

## Context

The product's approved visual direction requires a flat, monochrome interface. Gradient lighting and ambient drift conflict with the product's strict visual and frontend policy.

## Decision

Use solid Obsidian backgrounds; translucent glass with a solid 1 px border and a solid fallback; Pearl primary buttons and selected slots; and flat chart fills. Remove all CSS and SVG gradients, mask fades, gradient-clipped text, ambient lighting, and pointer-following sheen. Enforce the rule in the frontend policy scanner and browser coverage.

## Consequences

The interface retains blur, translucent fills, ordinary hover and press states, and visible focus rings. Figma effects that use gradients or ambient light are documented as visual overrides in `docs/design/figma.md`.
