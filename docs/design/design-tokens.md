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
| `--glass-top` | `surface/highlight` | `#ffffff3d` | Pearl tinted 24% → white at 23.9% |
| `--silver-light` | `chrome/tint/2-93/1000` | `#c9ced81a` | 10% → 10.2% Figma alpha |
| `--steel-light` | `chrome/tint/2-94/1200` | `#8a93a61f` | 12% → 12.2% Figma alpha |
| `--ambient-silver` (added) | `color/AmbientSilver` | `#c9ced8` | Separate ambient highlight from UI silver |
| `--glass-back` (added) | `surface/back` | `#ffffff0a` | Reusable translucent back surface |

The named color tokens, display/UI font families, type scale, panel/card/control radii, and 24/28/32 px blur values already match Figma. `--r-small` and `--space-half` were added as structural tokens for compact details. Font files remain self-hosted.

## CSP and visual limits

Figma's glass, ambient tints, silver button gradient, shadows, and motion can be expressed in external CSS under the strict CSP. No remote asset or image is needed for the auth frames. Backdrop blur is used only inside `@supports`; the solid Graphite surface remains the fallback. The Figma shared field copy says “At least 12 characters”, while the requested behavior and backend schema require 10; the UI says 10. The frames include a “Violet light field” layer name, but its bound value is monochrome silver `#c9ced81a`; the implementation uses the monochrome value. No visual effect needs an inline style, script, or data URI.

