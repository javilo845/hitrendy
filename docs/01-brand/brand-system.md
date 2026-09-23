---
id: BRAND-SYSTEM-001
kind: design_spec
status: accepted
related: [BRAND-TOKENS-001, UX-COMPONENTS-001]
---

# HiTrendy brand system

## Brand idea

HiTrendy should feel optimistic, creative, approachable, and useful. It is not a corporate analytics suite and not a childish toy. The visual language should communicate “friendly creative assistant” with enough structure to feel reliable.

## Positioning line

> Tu asistente para crear contenido que sí se parece a tu negocio.

## Personality

- Friendly, not overly casual.
- Creative, not chaotic.
- Clear, not technical.
- Encouraging, not exaggerated.
- Practical, not abstract.

## Existing visual assets retained

The supplied Figma establishes these recognizable elements:

- Hand-shaped smiling mascot.
- HiTrendy wordmark.
- Deep indigo surfaces.
- Violet and lavender accents.
- Rounded cards and controls.
- Bright promotional imagery.
- White or light neutral workspaces.

These elements should remain. The implementation adds consistency rather than redesigning the brand.

## Core palette

The palette was normalized from the supplied screenshots into semantic roles.

| Token | Hex | Use |
|---|---:|---|
| Ink 950 | `#180F4B` | Main dark background, navigation, primary text on lavender |
| Ink 900 | `#24105A` | Elevated dark panels |
| Violet 700 | `#541787` | Strong accent and active states |
| Violet 600 | `#6C24A8` | Gradient midpoint |
| Violet 500 | `#8B3FEF` | Primary interactive accent |
| Lavender 400 | `#B79CFA` | Decorative accents and secondary actions |
| Blue 600 | `#2D4BB6` | Supporting creative blue |
| Surface 50 | `#F8F6FC` | App background |
| Surface 100 | `#F0ECF7` | Subtle panels |
| Neutral 300 | `#DCD6E4` | Borders, disabled surfaces |
| Text 950 | `#191526` | Main text on light backgrounds |
| Text 600 | `#625B70` | Secondary text |
| White | `#FFFFFF` | Text on dark surfaces and cards |

## Gradients

### Hero gradient

```css
background: linear-gradient(145deg, #180F4B 0%, #24105A 48%, #6C24A8 100%);
```

### Primary button gradient

```css
background: linear-gradient(90deg, #A75AF4 0%, #7B2BE2 100%);
```

Use gradients sparingly. They are reserved for hero areas, major calls to action, and selected navigation—not every card.

## Typography

Use a modern geometric sans family available through the product deployment. Recommended hierarchy:

- Display and headings: `Poppins`, fallback `Inter`, sans-serif.
- Body and UI: `Inter`, fallback system sans-serif.

Do not bundle unlicensed font files. Use hosted or system-safe delivery according to deployment policy.

### Scale

- Display: 48/56, weight 700.
- H1: 36/44, weight 700.
- H2: 28/36, weight 700.
- H3: 22/30, weight 600.
- Body large: 18/28.
- Body: 16/24.
- Small: 14/20.
- Caption: 12/16.

## Shape language

- Main cards: 16px radius.
- Inputs and toolbars: 12px radius.
- Compact icon buttons: 10px radius.
- Pills: full radius.
- Avoid mixing sharp rectangles with heavily rounded elements.

## Elevation

- Dark cards should rely on border and tonal contrast rather than heavy shadow.
- Light floating panels use a soft two-layer shadow.
- Focus rings use Lavender 400 with sufficient contrast.

## Mascot usage

The hand mascot should appear in:

- logo lockup,
- empty states,
- onboarding success,
- limited decorative background placements.

Do not repeat it at full prominence on every section. Avoid reducing it below a size where the facial details disappear.

## Logo rules

- Preserve hand icon and wordmark proportions.
- Keep a clear space equal to the height of the hand’s central palm.
- On dark surfaces use white wordmark with lavender hand.
- On light surfaces use Ink 950 or Blue 600 wordmark.
- Do not apply additional shadows, outlines, or multiple gradients to the logo.
