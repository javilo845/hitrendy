---
id: AI-SKILLS-001
kind: ai_spec
status: accepted
related: [AI-ORCH-001]
---

# Skills catalog

A skill is a narrow, testable application capability. The LLM may assist inside a skill, but the skill contract belongs to HiTrendy.

## SKILL-001 `read_business_context`

**Purpose:** build a safe generation summary from business and brand records.

Input: workspace_id, business_id.

Output: `BusinessGenerationContext`.

No model required.

## SKILL-002 `classify_content_intent`

Input: user text and optional UI action.

Output:

- intent enum,
- confidence,
- missing critical fields.

Prefer deterministic UI action when present. Use model classification only for free text.

## SKILL-003 `generate_social_copy`

Input: business context, channel, objective, tone, product, user request.

Output: `GeneratedSocialPost` schema.

## SKILL-004 `rewrite_artifact`

Input: source artifact and explicit transformation.

Output: new artifact version and change summary.

## SKILL-005 `generate_short_video_script`

Output:

- hook,
- duration,
- scene list,
- on-screen text,
- voiceover,
- CTA,
- caption.

## SKILL-006 `analyze_visual_asset`

Input: an authorized, short-lived asset reference, business context, intended platform.

Output: `AssetAnalysis` schema.

In demo mode, this skill returns only verified technical metadata and explicit
human-review prompts. It must not claim to have interpreted the image. A vision
provider can replace that evaluator while preserving the output schema.

The provider must not receive a permanent public URL.

## SKILL-007 `recommend_templates`

Input: artifact type, platform, category, objective.

Output: ranked internal template IDs and rationale.

Use catalog filtering first; model reranking is optional.

## SKILL-008 `suggest_brand_profile`

Input: business onboarding responses and optional logo.

Output: voice adjectives, color-role suggestions, preferred/avoid terms, short brand statement.

Requires user approval before saving.

## SKILL-009 `save_project`

Input: artifact/version, title, template, assets.

Output: project ID and status.

No model required.

## SKILL-010 `trend_context` — optional later

Input: business category, location, date window.

Output: curated context with source links and timestamps.

This skill is behind a feature flag and not required for MVP acceptance.
