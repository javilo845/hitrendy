---
id: PROD-FLOWS-001
kind: product_spec
status: accepted
related: [FLOW-ONBOARD-001, FLOW-GEN-001, FLOW-ASSET-001, FLOW-SAVE-001]
---

# User flows

## FLOW-ONBOARD-001 — Business onboarding

1. User creates an account or enters demo mode.
2. User provides business name, category, location, products/services, target audience, preferred networks, and current objective.
3. User selects an existing visual identity or requests guided setup.
4. System creates a business profile and a default brand profile.
5. User lands on Home with suggested actions.

### Required fields

- Business name.
- Category.
- Country and city.
- Main product or service.
- Target audience.
- Main objective.
- At least one social platform.

### Optional fields

- Logo.
- Existing colors.
- Brand description.
- Website.
- Restrictions or words to avoid.

## FLOW-GEN-001 — Generate a publication

1. User selects “Crear publicación” or writes in chat.
2. Assistant detects intent and asks only for missing critical information.
3. Application builds generation context from the business profile and request.
4. LLM returns structured content.
5. System validates, quality-checks, and renders an editable result card.
6. User requests a variation, edits, copies, or saves.

### Output card

- Headline or hook.
- Main caption.
- Call to action.
- Hashtags.
- Visual suggestion.
- Recommended format.
- Optional publishing note.
- Assumptions used.

## FLOW-ASSET-001 — Review an uploaded design

1. User uploads PNG, JPG, or WebP.
2. Server validates type, size, dimensions, and ownership.
3. Vision provider receives the image and a restricted review rubric.
4. Output is validated into strengths, improvements, priority, and revised copy.
5. User can save the review with the asset.

### Review rubric

- Message clarity.
- Visual hierarchy.
- Readability.
- Brand consistency.
- Call-to-action visibility.
- Platform suitability.
- Accessibility risks.

## FLOW-TEMPLATE-001 — Recommend a template

1. User selects artifact type and platform.
2. Recommendation service filters templates by aspect ratio, use case, category, and complexity.
3. Results show preview, title, supported formats, and “Usar plantilla”.
4. Selected template opens as a project with editable copy fields.

## FLOW-SAVE-001 — Save as project

1. User selects “Guardar proyecto”.
2. System persists artifact, edits, source conversation, business profile version, and template reference.
3. Project appears under “Tus proyectos”.
4. User can reopen without regenerating.

## FLOW-VARIANT-001 — Create variations

1. User chooses a variation control: shorter, more youthful, more professional, or friendlier.
2. System sends the original artifact plus requested delta, not the entire conversation.
3. New version is linked to the original.
4. User compares and promotes one version as current; promotion creates a new
   version, so no historical content is overwritten.

## Flow principles

- Ask the fewest possible questions.
- Never lose user edits during regeneration.
- Avoid blank screens; present quick actions.
- Explain missing context in simple language.
- Keep generated content separate from assistant commentary.
