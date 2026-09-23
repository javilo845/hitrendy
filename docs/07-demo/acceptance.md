---
id: DEMO-ACCEPT-001
kind: acceptance_spec
status: accepted
---

# MVP acceptance criteria

## AC-001 Onboarding

Given a new user, when required business data is completed, then a business and brand profile are persisted and shown as active.

## AC-002 Personalized generation

Given an active business profile, when the user requests an Instagram post, then the result includes the business/product context, requested tone, CTA, and no more than five hashtags.

## AC-003 Missing facts

Given no price or discount, the generated result must not invent one.

## AC-004 Structured rendering

The frontend renders the result from a typed artifact object, not by parsing an arbitrary assistant paragraph.

## AC-005 Edit safety

When the user edits a generated caption and creates a variation, the original edited version remains available.

## AC-006 Project persistence

A saved project appears in the project list and reopens with its current version.

## AC-007 Upload control

Unsupported or oversized files are rejected before AI-provider execution.

## AC-008 Visual feedback

A valid image can receive strengths and prioritized improvements in a stable card format.

## AC-009 Provider independence

Switching from demo provider to a configured provider does not change API response contracts.

## AC-010 Demo resilience

The core demo works without network access to an AI provider.

## AC-011 Authorization

A user cannot access another workspace’s business, conversation, asset, or project by changing an ID.

## AC-012 Accessibility

The complete demo flow is keyboard-operable, and icon-only actions have accessible names.
