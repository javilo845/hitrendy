from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.core.errors import AppError
from app.domain.models import (
    BusinessGenerationContext,
    GeneratedShortVideoScript,
    GeneratedSocialPost,
)
from app.generation.contracts import (
    AdvisorModelRequest,
    ShortVideoScriptModelRequest,
    SocialPostModelRequest,
)
from app.providers.content import DemoContentModelProvider, OpenAICompatibleContentModelProvider

API_KEY = "sentinel-api-key-do-not-expose"
RAW_BODY = "provider-internal-body-do-not-expose"


def _business() -> BusinessGenerationContext:
    return BusinessGenerationContext(
        business_id="business-provider-test",
        name="Café Aurora",
        category="gastronomy",
        city="Tegucigalpa",
        country="Honduras",
        primary_product="café frío artesanal",
        target_audience="jóvenes profesionales",
        preferred_platforms=["instagram", "tiktok"],
        primary_objective="engagement",
        brand_tones=["friendly", "professional"],
        value_proposition="Bebidas artesanales preparadas al momento.",
        preferred_words=["artesanal"],
        forbidden_words=["milagroso"],
    )


def _social_request() -> SocialPostModelRequest:
    business = _business()
    return SocialPostModelRequest(
        business=business,
        user_request="Crea una publicación breve en español.",
        platform="instagram",
        tone="friendly",
        objective="engagement",
        prompt_version="test-provider@1.0.0",
        product_or_service=business.primary_product,
    )


def _video_request() -> ShortVideoScriptModelRequest:
    business = _business()
    return ShortVideoScriptModelRequest(
        business=business,
        user_request="Crea un guion vertical breve en español.",
        platform="tiktok",
        tone="friendly",
        objective="engagement",
        prompt_version="test-provider@1.0.0",
        product_or_service=business.primary_product,
    )


def _social_payload() -> dict[str, object]:
    return {
        "artifact_type": "social_post",
        "platform": "instagram",
        "hook": "Una pausa fresca para tu día",
        "caption": "Conoce nuestro café frío artesanal.",
        "call_to_action": "Cuéntanos qué te parece.",
        "hashtags": ["#CafeFrio"],
        "visual_direction": "Producto claro con luz natural.",
        "format_recommendation": "reel",
        "assumptions": ["Se utilizó el tono amistoso del perfil."],
    }


def _video_payload() -> dict[str, object]:
    return {
        "artifact_type": "short_video_script",
        "platform": "tiktok",
        "hook": "Así se disfruta el café frío",
        "duration_seconds": 20,
        "scenes": [
            {
                "order": 1,
                "duration_seconds": 8,
                "visual": "Primer plano del café.",
                "on_screen_text": "Café frío artesanal",
                "voiceover": "Conoce una pausa diferente.",
            },
            {
                "order": 2,
                "duration_seconds": 12,
                "visual": "Una persona disfruta la bebida.",
                "on_screen_text": "Disfrútalo hoy",
                "voiceover": "Visítanos y pruébalo.",
            },
        ],
        "call_to_action": "Visítanos hoy.",
        "caption": "Una pausa diferente con café frío.",
        "assumptions": ["Se utilizó el objetivo del perfil."],
    }


def _envelope(content: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}


def _provider(
    handler: Callable[[httpx.Request], httpx.Response | Exception],
    *,
    max_retries: int = 1,
    sleep_calls: list[float] | None = None,
    http_referer: str = "https://hitrendy.example",
) -> OpenAICompatibleContentModelProvider:
    async def transport_handler(request: httpx.Request) -> httpx.Response:
        result = handler(request)
        if isinstance(result, Exception):
            raise result
        return result

    async def sleep(delay: float) -> None:
        if sleep_calls is not None:
            sleep_calls.append(delay)

    return OpenAICompatibleContentModelProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
        model_name="test-model",
        timeout_seconds=0.1,
        max_retries=max_retries,
        retry_base_seconds=0.5,
        http_referer=http_referer,
        app_title="HiTrendy Test",
        transport=httpx.MockTransport(transport_handler),
        sleep=sleep,
    )


@pytest.mark.asyncio
async def test_demo_provider_requires_no_credentials_and_returns_valid_artifacts() -> None:
    provider = DemoContentModelProvider()

    social = await provider.generate_social_post(request=_social_request())
    video = await provider.generate_short_video_script(request=_video_request())

    assert GeneratedSocialPost.model_validate(social).caption
    assert GeneratedShortVideoScript.model_validate(video).scenes


@pytest.mark.asyncio
async def test_openai_provider_decodes_valid_json_and_sends_expected_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_envelope(_social_payload()))

    provider = _provider(handler)
    result = await provider.generate_social_post(request=_social_request())

    assert result == _social_payload()
    request = requests[0]
    body = json.loads(request.content)
    assert request.url == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert request.headers["http-referer"] == "https://hitrendy.example"
    assert request.headers["x-title"] == "HiTrendy Test"
    assert body["model"] == "test-model"
    assert body["messages"]
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openrouter_uses_strict_json_schema_for_advisor_and_copywriter() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = (
            {"summary": "Plan", "recommendations": [], "next_actions": ["Publica hoy."]}
            if len(requests) == 1
            else _social_payload()
        )
        return httpx.Response(200, json=_envelope(content))

    async def transport_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    provider = OpenAICompatibleContentModelProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
        model_name="openrouter/free",
        provider_name="openrouter",
        structured_output=True,
        transport=httpx.MockTransport(transport_handler),
    )
    await provider.generate_advice(
        request=AdvisorModelRequest(
            business=_business(), locale="es", user_request="Da una recomendación."
        )
    )
    await provider.generate_social_post(request=_social_request())

    advisor_format = json.loads(requests[0].content)["response_format"]
    post_format = json.loads(requests[1].content)["response_format"]
    assert advisor_format["type"] == post_format["type"] == "json_schema"
    assert advisor_format["json_schema"]["strict"] is True
    assert post_format["json_schema"]["strict"] is True
    assert advisor_format["json_schema"]["schema"]["title"] == "AdvisorResponse"
    assert post_format["json_schema"]["schema"]["title"] == "GeneratedSocialPost"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected_cta_fragment", "spanish_fragment"),
    [
        ("es", "Cuéntanos", None),
        ("en", "Tell us", "Cuéntanos"),
        ("pt", "Conte para nós", "Cuéntanos"),
    ],
)
async def test_demo_provider_honors_locale_and_brand_words(
    locale: str, expected_cta_fragment: str, spanish_fragment: str | None
) -> None:
    provider = DemoContentModelProvider()
    business = _business().model_copy(
        update={"preferred_words": ["artesanal"], "forbidden_words": ["milagroso"]}
    )
    request = _social_request().model_copy(update={"business": business, "locale": locale})
    advisor = await provider.generate_advice(
        request=AdvisorModelRequest(business=business, locale=locale, user_request="Ayúdame")
    )
    social = await provider.generate_social_post(request=request)

    assert expected_cta_fragment in social["call_to_action"]
    assert "artesanal" in social["caption"].casefold()
    assert "milagroso" not in str(social).casefold()
    assert "milagroso" not in str(advisor).casefold()
    if spanish_fragment:
        assert spanish_fragment not in str(social)
        assert spanish_fragment not in str(advisor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (httpx.ReadTimeout("timeout"), "GENERATION_PROVIDER_TIMEOUT"),
        (httpx.ConnectError("network"), "GENERATION_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_openai_provider_retries_transient_transport_errors(
    failure: Exception, expected_code: str
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response | Exception:
        nonlocal calls
        calls += 1
        return failure if calls == 1 else httpx.Response(200, json=_envelope(_social_payload()))

    provider = _provider(handler, sleep_calls=delays)
    result = await provider.generate_social_post(request=_social_request())

    assert result == _social_payload()
    assert calls == 2
    assert delays == [0.5]


@pytest.mark.asyncio
async def test_openai_provider_network_exhaustion_is_bounded() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> Exception:
        nonlocal calls
        calls += 1
        return httpx.ConnectError(f"{RAW_BODY} {API_KEY}")

    provider = _provider(handler, max_retries=2, sleep_calls=delays)

    with pytest.raises(AppError) as caught:
        await provider.generate_social_post(request=_social_request())

    assert caught.value.code == "GENERATION_PROVIDER_UNAVAILABLE"
    assert caught.value.status_code == 503
    assert caught.value.retryable is True
    assert calls == 3
    assert delays == [0.5, 1.0]
    assert API_KEY not in f"{caught.value} {caught.value.detail}"
    assert RAW_BODY not in f"{caught.value} {caught.value.detail}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (429, "GENERATION_PROVIDER_RATE_LIMITED"),
        (500, "GENERATION_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_openai_provider_retries_rate_limit_and_server_errors(
    status_code: int, expected_code: str
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text=RAW_BODY)

    provider = _provider(handler, max_retries=2, sleep_calls=delays)

    with pytest.raises(AppError) as caught:
        await provider.generate_social_post(request=_social_request())

    assert caught.value.code == expected_code
    assert caught.value.status_code == (429 if status_code == 429 else 503)
    assert caught.value.retryable is True
    assert calls == 3
    assert delays == [0.5, 1.0]


@pytest.mark.asyncio
async def test_openai_provider_timeout_exhaustion_is_bounded_and_sanitized() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> Exception:
        nonlocal calls
        calls += 1
        return httpx.ReadTimeout(f"{RAW_BODY} {API_KEY}")

    provider = _provider(handler, max_retries=2, sleep_calls=delays)

    with pytest.raises(AppError) as caught:
        await provider.generate_social_post(request=_social_request())

    assert caught.value.code == "GENERATION_PROVIDER_TIMEOUT"
    assert caught.value.status_code == 504
    assert caught.value.retryable is True
    assert calls == 3
    assert delays == [0.5, 1.0]
    public = f"{caught.value} {caught.value.detail}"
    assert API_KEY not in public
    assert RAW_BODY not in public


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_openai_provider_does_not_retry_permanent_provider_errors(status_code: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text=f"{RAW_BODY} {API_KEY}")

    provider = _provider(handler, max_retries=2)

    with pytest.raises(AppError) as caught:
        await provider.generate_social_post(request=_social_request())

    assert caught.value.code == "GENERATION_PROVIDER_REJECTED"
    assert caught.value.status_code == 502
    assert caught.value.retryable is False
    assert calls == 1
    public = f"{caught.value} {caught.value.detail}"
    assert API_KEY not in public
    assert RAW_BODY not in public


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{}]}),
        httpx.Response(200, json={"choices": [{"message": None}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": ["no"]}}]}),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        ),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(["not-an-object"])}}]},
        ),
    ],
    ids=[
        "invalid-http-json",
        "non-object-envelope",
        "missing-choices",
        "empty-choices",
        "missing-message",
        "empty-content",
        "non-string-content",
        "invalid-content-json",
        "non-object-content",
        "extra-invalid-content",
    ],
)
async def test_openai_provider_rejects_malformed_response_without_leaking_body(
    response: httpx.Response,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    provider = _provider(handler, max_retries=2)

    with pytest.raises(AppError) as caught:
        await provider.generate_social_post(request=_social_request())

    assert caught.value.code == "GENERATION_PROVIDER_INVALID_RESPONSE"
    assert caught.value.status_code == 502
    assert caught.value.retryable is True
    public = f"{caught.value} {caught.value.detail}"
    assert API_KEY not in public
    assert RAW_BODY not in public


@pytest.mark.asyncio
async def test_openai_provider_propagates_cancellation_without_retry() -> None:
    started = asyncio.Event()
    calls = 0

    async def transport_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=_envelope(_social_payload()))

    provider = OpenAICompatibleContentModelProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
        model_name="test-model",
        max_retries=2,
        transport=httpx.MockTransport(transport_handler),
        sleep=lambda delay: asyncio.sleep(0),
    )
    task = asyncio.create_task(provider.generate_social_post(request=_social_request()))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == 1
