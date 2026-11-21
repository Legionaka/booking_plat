# F1 design token reconciliation

Source: Figma Design system page `Design system`, especially `Color tokens`, `Ambient light and glass depths`, and `Typography and shape`; auth frame variables were read from customer sign-in, registration, verify, forgot, and reset frames.

## CSS token changes

Existing public token names were preserved. Values below now match Figma variables:

| CSS token | Figma variable | Figma value | Change |
|---|---|---:|---|
| `--glass` | `surface/card` | `#ffffff0d` | Pearl tinted 5% overlay → white at 5.1% |
| `--glass-background-fill` | `surface/back` | `#ffffff0a` | Pearl tinted 4% → white at 3.9% |
| `--glass-floating-fill` | `surface/floating` | `#ffffff0f` | Pearl tinted 6% → white at 5.9% |
| `--glass-border` | `surface/border` | `#ffffff1a` | Pearl tinted 10% → white at 10.2% |
| `--glass-back` (added) | `surface/back` | `#ffffff0a` | Reusable translucent back surface |
| `--scrim` (added) | modal backdrop | Obsidian at 72% | Shared dialog and palette backdrop |

The named color tokens, display/UI font families, type scale, panel/card/control radii, and 24/28/32 px blur values already match Figma. `--r-small` and `--space-half` were added as structural tokens for compact details. Font files remain self-hosted.

## CSP and visual limits

Figma glass uses a translucent white fill, solid 1 px border, and backdrop blur under strict CSP. The global flat-style override removes gradients, light fields, highlights, glows, and pointer-following sheen. Graphite is the solid fallback when blur is unavailable. The Figma shared field copy says “At least 12 characters”, while the requested behavior and backend schema require 10; the UI says 10. No visual effect needs an inline style, script, or data URI.

