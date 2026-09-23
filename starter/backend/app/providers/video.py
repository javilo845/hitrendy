"""Provider boundary for asynchronous video generation.

The interface keeps the application independent from vendors. The demo stays
deterministic and offline, while the optional OpenAI adapter owns all network
and paid-provider details behind the same port.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from importlib import resources
from typing import Any, Protocol

import httpx
from PIL import Image, ImageOps

from app.core.config import settings
from app.core.errors import AppError

_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,191}$")


@dataclass(frozen=True, slots=True)
class VideoGenerationRequest:
    prompt: str
    negative_prompt: str | None
    storyboard: dict[str, Any]
    aspect_ratio: str
    duration_seconds: int
    model: str
    source_image: bytes | None
    source_image_mime: str | None


@dataclass(frozen=True, slots=True)
class VideoSubmission:
    provider_job_id: str
    provider_status: str


@dataclass(frozen=True, slots=True)
class VideoJobState:
    provider_status: str
    ready: bool
    failed: bool
    error_code: str | None
    error_message: str | None
    cost_units: int | None


@dataclass(frozen=True, slots=True)
class VideoArtifact:
    content: bytes
    mime_type: str


class VideoGenerationProvider(Protocol):
    name: str

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission: ...

    async def check(self, provider_job_id: str) -> VideoJobState: ...

    async def download(self, provider_job_id: str, *, duration_seconds: int) -> VideoArtifact: ...

    async def cancel(self, provider_job_id: str) -> bool: ...


_DEMO_FIXTURES: dict[int, str] = {
    5: "demo-9x16-5s.mp4",
    10: "demo-9x16-10s.mp4",
}


def _canonical_request(request: VideoGenerationRequest) -> str:
    payload = {
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "storyboard": request.storyboard,
        "aspect_ratio": request.aspect_ratio,
        "duration_seconds": request.duration_seconds,
        "model": request.model,
        "source_image": (
            base64.b64encode(request.source_image).decode("ascii")
            if request.source_image is not None
            else None
        ),
        "source_image_mime": request.source_image_mime,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DemoVideoGenerationProvider:
    """Deterministic fixture-backed provider for development and tests."""

    name = "demo"

    def __init__(self) -> None:
        if settings.app_env not in {"development", "test"}:
            raise RuntimeError("VIDEO_PROVIDER=demo solo está permitido en desarrollo y pruebas.")

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        canonical = _canonical_request(request)
        request_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        # The fixture output is deterministic, but each submitted job still
        # needs its own provider handle: the durable job table correctly
        # rejects two different requests with one provider_job_id.
        provider_job_id = f"demo_{request_digest}_{uuid.uuid4().hex}"
        return VideoSubmission(provider_job_id=provider_job_id, provider_status="pending")

    async def check(self, provider_job_id: str) -> VideoJobState:
        _ = provider_job_id
        return VideoJobState(
            provider_status="ready",
            ready=True,
            failed=False,
            error_code=None,
            error_message=None,
            cost_units=1,
        )

    async def download(self, provider_job_id: str, *, duration_seconds: int) -> VideoArtifact:
        _ = provider_job_id
        try:
            fixture_name = _DEMO_FIXTURES[duration_seconds]
        except KeyError as exc:
            raise ValueError("La duración no tiene una fixture demo exacta.") from exc
        fixture = resources.files("app.videos.fixtures").joinpath(fixture_name)
        return VideoArtifact(content=fixture.read_bytes(), mime_type="video/mp4")

    async def cancel(self, provider_job_id: str) -> bool:
        _ = provider_job_id
        return False


class OpenAIVideoGenerationProvider:
    """OpenAI Videos API adapter for the asynchronous Sora workflow.

    A submit is never retried: a timeout after ``POST /videos`` is ambiguous
    and the worker must preserve that ambiguity instead of creating a second
    paid render. Status checks and downloads are idempotent and remain behind
    the durable worker state machine.
    """

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _size(self, request: VideoGenerationRequest) -> str:
        # The pro route is the documented 1080p export. The faster route uses
        # the smaller vertical canvas to keep a fair demo within a reasonable
        # latency and spend envelope.
        if request.model.endswith("-pro"):
            return "1080x1920" if request.aspect_ratio == "9:16" else "1920x1080"
        return "720x1280" if request.aspect_ratio == "9:16" else "1280x720"

    @staticmethod
    def _prompt(request: VideoGenerationRequest) -> str:
        parts = [request.prompt.strip()]
        shots = request.storyboard.get("shots")
        if isinstance(shots, list):
            shot_lines: list[str] = []
            for raw_shot in shots[:8]:
                if not isinstance(raw_shot, dict):
                    continue
                order = raw_shot.get("order")
                visual = raw_shot.get("visual")
                camera = raw_shot.get("camera")
                voiceover = raw_shot.get("voiceover")
                line = f"Toma {order}: {visual}. Cámara: {camera}."
                if isinstance(voiceover, str) and voiceover.strip():
                    line += f" Voz: {voiceover.strip()}."
                if isinstance(order, int) and isinstance(visual, str) and isinstance(camera, str):
                    shot_lines.append(line)
            if shot_lines:
                parts.append("Storyboard editable:\n" + "\n".join(shot_lines))
        if request.negative_prompt:
            parts.append(f"Evita: {request.negative_prompt.strip()}")
        # The application contract already limits the prompt, but keep the
        # provider payload bounded after adding the editable storyboard.
        return "\n\n".join(part for part in parts if part)[:32_000]

    @staticmethod
    def _reference_image(content: bytes, size: str) -> tuple[bytes, str]:
        try:
            width, height = (int(value) for value in size.split("x", 1))
            with Image.open(io.BytesIO(content)) as image:
                fitted = ImageOps.fit(
                    image.convert("RGB"),
                    (width, height),
                    method=Image.Resampling.LANCZOS,
                )
                output = io.BytesIO()
                fitted.save(output, format="JPEG", quality=90, optimize=True)
        except (OSError, ValueError) as exc:
            raise AppError(
                "VIDEO_PROVIDER_REJECTED",
                "La imagen de referencia no se pudo preparar para el video.",
                status_code=422,
            ) from exc
        return output.getvalue(), "image/jpeg"

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        size = self._size(request)
        data = {
            "model": request.model or self._model_name,
            "prompt": self._prompt(request),
            "size": size,
            "seconds": str(request.duration_seconds),
        }
        files = None
        if request.source_image:
            image_bytes, mime_type = self._reference_image(request.source_image, size)
            files = {"input_reference": ("reference.jpg", image_bytes, mime_type)}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/videos",
                    headers=self._headers(),
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "VIDEO_PROVIDER_TIMEOUT",
                "La solicitud de video tardó demasiado. Revisaremos su estado antes de reintentar.",
                status_code=504,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AppError(
                "VIDEO_PROVIDER_UNAVAILABLE",
                "La generación de video no está disponible en este momento.",
                status_code=503,
                retryable=True,
            ) from exc
        if response.status_code >= 400:
            raise _map_video_status_error(response)
        try:
            body = response.json()
            provider_job_id = body["id"]
            provider_status = body.get("status", "queued")
            if not isinstance(provider_job_id, str) or not _PROVIDER_ID.fullmatch(provider_job_id):
                raise ValueError("missing video id")
            if not isinstance(provider_status, str) or not provider_status:
                provider_status = "queued"
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                "El proveedor no devolvió una referencia de video válida.",
                status_code=502,
                retryable=True,
            ) from exc
        return VideoSubmission(
            provider_job_id=provider_job_id,
            provider_status=provider_status[:48],
        )

    async def check(self, provider_job_id: str) -> VideoJobState:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/videos/{provider_job_id}", headers=self._headers()
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "VIDEO_PROVIDER_TIMEOUT",
                "No pudimos consultar el estado del video.",
                status_code=504,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AppError(
                "VIDEO_PROVIDER_UNAVAILABLE",
                "No pudimos consultar el estado del video.",
                status_code=503,
                retryable=True,
            ) from exc
        if response.status_code >= 400:
            if response.status_code == 404:
                return VideoJobState(
                    provider_status="not_found",
                    ready=False,
                    failed=True,
                    error_code="provider_not_found",
                    error_message="El proveedor ya no encuentra este video.",
                    cost_units=1,
                )
            raise _map_video_status_error(response)
        try:
            body = response.json()
            status = body["status"]
            if not isinstance(status, str):
                raise ValueError("invalid status")
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                "El proveedor no devolvió un estado de video válido.",
                status_code=502,
                retryable=True,
            ) from exc

        normalized = status[:48]
        if status == "completed":
            return VideoJobState(normalized, True, False, None, None, 1)
        if status in {"queued", "in_progress"}:
            return VideoJobState(normalized, False, False, None, None, None)
        return VideoJobState(
            normalized,
            False,
            True,
            "provider_failed",
            "El proveedor no pudo completar el video.",
            1,
        )

    async def download(self, provider_job_id: str, *, duration_seconds: int) -> VideoArtifact:
        _ = duration_seconds
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/videos/{provider_job_id}/content",
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "VIDEO_PROVIDER_TIMEOUT",
                "La descarga del video tardó demasiado.",
                status_code=504,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AppError(
                "VIDEO_PROVIDER_UNAVAILABLE",
                "No pudimos descargar el video generado.",
                status_code=503,
                retryable=True,
            ) from exc
        if response.status_code >= 400:
            raise _map_video_status_error(response)
        content = response.content
        if not content or len(content) > settings.video_generation_max_bytes:
            raise AppError(
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                "El proveedor no devolvió un video válido.",
                status_code=502,
                retryable=True,
            )
        return VideoArtifact(content=content, mime_type="video/mp4")

    async def cancel(self, provider_job_id: str) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.delete(
                    f"{self._base_url}/videos/{provider_job_id}", headers=self._headers()
                )
        except httpx.RequestError:
            return False
        return response.status_code in {200, 204, 404}


def _map_video_status_error(response: httpx.Response) -> AppError:
    status = response.status_code
    if status == 402:
        return AppError(
            "PAYMENT_REQUIRED",
            "Esta generación de video requiere presupuesto habilitado.",
            status_code=402,
        )
    if status == 429:
        return AppError(
            "VIDEO_PROVIDER_RATE_LIMITED",
            "El proveedor de video está ocupado. Inténtalo nuevamente en unos minutos.",
            status_code=429,
            retryable=True,
        )
    if status >= 500:
        return AppError(
            "VIDEO_PROVIDER_UNAVAILABLE",
            "La generación de video no está disponible en este momento.",
            status_code=503,
            retryable=True,
        )
    return AppError(
        "VIDEO_PROVIDER_REJECTED",
        "El proveedor rechazó la solicitud de video.",
        status_code=status,
    )
