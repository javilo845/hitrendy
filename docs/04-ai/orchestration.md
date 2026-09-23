---
id: AI-ORCH-001
kind: ai_spec
status: accepted
related: [FLOW-GEN-001, ADR-003]
---

# AI orchestration

## MVP recommendation

Start with a deterministic workflow, not an unconstrained autonomous agent. A graph runtime may be used when it improves retries, persistence, or branching.

## Generation state

```python
class GenerationState(TypedDict):
    request_id: str
    workspace_id: str
    business_id: str
    conversation_id: str
    user_text: str
    intent: str | None
    missing_fields: list[str]
    business_context: dict
    attachment_context: list[dict]
    model_request: dict
    raw_output: dict | None
    validated_artifact: dict | None
    evaluation: dict | None
    retry_count: int
    error: str | None
```

## Workflow

```mermaid
flowchart TD
  A[Receive request] --> B[Authorize and validate]
  B --> C[Classify intent]
  C --> D[Load business and brand context]
  D --> E{Critical context missing?}
  E -- yes --> F[Return clarification]
  E -- no --> G[Build structured model request]
  G --> H[Call content provider]
  H --> I[Validate schema]
  I --> J{Valid?}
  J -- no --> K[Repair once]
  J -- yes --> L[Evaluate quality]
  K --> L
  L --> M{Meets threshold?}
  M -- no --> N[Targeted revision once]
  M -- yes --> O[Persist artifact and metadata]
  N --> O
  O --> P[Return renderable artifact]
```

## Why not a free-form agent

A free-form agent can make unnecessary tool calls, increase latency, and behave inconsistently. HiTrendy has a small set of predictable capabilities, so the application should own the flow.

## LangGraph integration point

Use LangGraph when adding:

- resumable jobs,
- human approval,
- parallel image and copy analysis,
- provider fallbacks,
- multi-step campaign generation.

The graph should call application services. It should not become the domain model.

## Context budget

Include only:

- normalized business summary,
- relevant brand rules,
- current user request,
- last few relevant messages or a conversation summary,
- selected asset analysis,
- output schema instructions.

Do not send the entire user history by default.

## Retry policy

- Network/provider retry: up to two with backoff.
- Schema repair: one.
- Quality revision: one.
- Never silently loop indefinitely.

## Current implementation boundary

Social-post generation builds a typed `SocialPostModelRequest` from authorized business context and the current user request. It validates the provider response with `GeneratedSocialPost`, performs at most one schema repair and one quality repair, then persists the provider/model/prompt metadata with the artifact. The current deterministic evaluator checks platform, CTA, and forbidden brand terms; the full rubric suite remains the next quality increment.
