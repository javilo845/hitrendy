---
id: BRAND-A11Y-001
kind: quality_spec
status: accepted
---

# Accessibility requirements

## Minimum target

Build toward WCAG 2.2 AA for the primary flows.

## Color

- Do not use violet-on-violet combinations for body text.
- White text on Ink 950 is preferred for dark surfaces.
- Lavender 400 is decorative or large-text accent, not small body text on white.
- Status must never be communicated only by color.

## Keyboard

- All controls must be reachable and usable by keyboard.
- Sidebar icons need visible focus and accessible names.
- Dialog focus is trapped and restored on close.
- Message actions are available without hover.

## Forms

- Every field has a programmatic label.
- Errors are associated with the field and announced.
- Required fields are explained in text.
- Checkbox groups use fieldsets and legends.

## Chat

- New assistant messages use a polite live region.
- Streaming updates should not announce every token.
- The final completed message is announced once.
- Generated result cards have explicit headings and actions.

## Images

- Uploaded and generated images require alt text before export.
- Decorative assets use empty alt attributes.
- Template previews have descriptive labels.

## Motion and media

- Respect reduced motion.
- Voice input always has visible state and a stop control.
- Video previews do not autoplay with sound.
