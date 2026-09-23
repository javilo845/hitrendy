---
id: API-PROVIDERS-001
kind: architecture_spec
status: accepted
related: [NFR-003]
---

# Provider interfaces

## Content model provider

```python
class ContentModelProvider(Protocol):
    provider_name: str
    model_name: str

    async def generate_social_post(
        self, *, request: SocialPostModelRequest
    ) -> dict: ...

    async def repair_social_post(
        self, *, request: SocialPostModelRequest,
        invalid_output: dict, errors: list[str]
    ) -> dict: ...
```

The provider returns untrusted dictionaries. The application validates them.

## Provider implementations

- `DemoContentProvider`: deterministic and offline for development/tests.
- `OpenAICompatibleProvider`: implemented through `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL`; when the endpoint is OpenAI, `OPENAI_API_KEY` is accepted as the shared-key fallback.
- `OllamaProvider`: planned local-model adapter.
- Additional cloud providers may be added without changing domain services.

Providers receive a bounded `SocialPostModelRequest`, never a database session, user session, tool registry, or raw conversation history. They return untrusted dictionaries; the application validates, evaluates, repairs once when needed, and persists only the final artifact.

## Object storage provider

```python
class ObjectStorageProvider(Protocol):
    async def put(self, *, key: str, content: bytes, content_type: str) -> None: ...
    async def read(self, *, key: str) -> bytes: ...
    async def delete(self, *, key: str) -> None: ...
```

The application generates opaque workspace-scoped keys and authorizes every
content read before calling the provider. `LocalObjectStorageProvider` is for
development only; production uses the `s3` adapter configured through the
object-storage environment variables. A future direct-upload implementation
may add signed upload targets without exposing permanent read URLs.

## Visual review provider

```python
class VisionReviewProvider(Protocol):
    provider_name: str
    requires_image_content: bool

    async def analyze(self, *, request: VisionReviewRequest) -> dict: ...
```

`DemoVisionReviewProvider` is the default offline implementation. It receives
only verified image metadata and makes no claim to have interpreted pixels.
`OpenAICompatibleVisionReviewProvider` is enabled only with
`VISION_PROVIDER=openai-compatible` and its own `VISION_BASE_URL`,
`VISION_API_KEY`, and `VISION_MODEL` settings. `OPENAI_API_KEY` can supply the
key and base URL when those fields are omitted. This deliberate separation
from the text provider prevents an image from leaving HiTrendy merely because
text generation uses an external model.

Image and video generation use separate asynchronous ports. The direct OpenAI
adapters are selected with `IMAGE_PROVIDER=openai` and `VIDEO_PROVIDER=openai`;
they receive only the approved prompt, storyboard and validated bytes. The
operator allowlists the paid model explicitly before a job can be confirmed.

Before invoking a provider, the application authorizes the asset inside its
workspace and reads its private object content. The adapter sends bounded image
bytes plus technical metadata; it never receives a permanent URL, storage key,
workspace ID, user session, or database access. Its untrusted JSON response is
validated against `AssetAnalysis` before persistence or display.

## Template catalog provider

MVP uses internal database records and local/static previews. A future remote catalog must map into the same internal `Template` contract.

## Authentication provider

Authentication may be self-managed or delegated, but application authorization remains internal. External identity IDs must map to HiTrendy user and workspace records.
