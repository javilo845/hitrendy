---
id: PROD-VISION-001
kind: product_spec
status: accepted
related: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006]
---

# Vision and scope

## Product statement

HiTrendy is a web assistant for entrepreneurs, small businesses, and creators who need help planning and producing social-media content without requiring professional marketing or design experience.

It turns a simple business profile and a conversational request into editable content: captions, post ideas, campaign concepts, short scripts, calls to action, visual briefs, template recommendations, and constructive feedback on uploaded designs.

## Primary users

1. Micro and small business owner managing social accounts personally.
2. Employee responsible for social media without formal marketing training.
3. Independent creator offering products or services.
4. Student entrepreneur preparing promotional material.

## User problem

The user knows the business but often lacks time, confidence, strategy, or writing skill. Generic AI tools require repeated context and produce answers that may not match the brand. Design tools provide templates but not business-aware guidance.

## Core promise

> Tell HiTrendy what you sell and what you need. It will help you create a useful publication in your brand voice and keep it organized as a project.

## Product pillars

### 1. Personalized

Every generation uses the active business profile, target audience, preferred channels, tone, objective, and brand identity.

### 2. Conversational

The main interaction is a chat, but the interface supplies quick actions and guided fields so users do not need prompt-engineering knowledge.

### 3. Actionable

The output must be immediately useful and editable, not a long marketing essay.

### 4. Visual

Generated content can be paired with a template or creative brief. Uploaded graphics can receive practical feedback.

### 5. Progressive

The MVP focuses on content assistance. Trend context, advanced analytics, publishing integrations, and image generation are optional later modules.

## MVP capabilities

- Authentication and workspace.
- Business onboarding and brand profile.
- Chat history.
- Social copy generation.
- Rewrite by tone or objective.
- Short-video script generation.
- Template recommendations.
- Upload an image and receive structured feedback.
- Save, edit, duplicate, archive, and export a project.
- Library of user assets and generated content.
- Demo provider that works offline.

## Out of scope

- Social-platform account management.
- Automatic publication scheduling.
- Scraping private or restricted content.
- Full design canvas.
- Real-time market intelligence.
- Automatic model training on user conversations.
- Guaranteed marketing results.

## Success metrics

### Activation

At least 70% of new demo users complete onboarding and generate one artifact.

### Time to value

Median time from first login to first saved artifact under five minutes.

### Quality

At least 80% of evaluated outputs satisfy the requested platform, tone, audience, and objective.

### Usability

A user can complete the main flow without written instructions from the presenter.

## Product risks

- Becoming a generic chatbot.
- Overpromising automated trends or social integrations.
- Producing content that ignores the business context.
- Adding a Canva-like editor before the content workflow is stable.
- Treating model fluency as factual correctness.

## Guardrail against generic chat

Every generation request must resolve these fields before calling a model:

- business_id
- objective
- platform
- audience
- tone
- requested_artifact_type
- product_or_service
- call_to_action or explicit `none`

The assistant may infer missing values from the business profile, but the result must disclose the inferred assumptions in structured metadata.
