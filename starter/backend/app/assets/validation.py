"""Shared image validation for every byte string that reaches storage.

Uploads and generated images are validated identically: a provider response is
as untrusted as a browser upload, so it passes the same format allow-list,
size ceiling, decompression-bomb guard and expansion-ratio guard.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import ValidationError_

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class ImageMetadata:
    mime_type: str
    extension: str
    width: int
    height: int


def read_image_metadata(content: bytes) -> ImageMetadata | None:
    """Return trustworthy metadata, or ``None`` when the bytes are not a safe image."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.verify()
                mime_type, extension = _FORMATS[image.format or ""]
                return ImageMetadata(mime_type, extension, image.width, image.height)
    except (
        KeyError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ):
        return None


def validate_image_bytes(
    content: bytes,
    declared_mime_type: str | None,
    *,
    max_bytes: int | None = None,
    size_message: str | None = None,
) -> ImageMetadata:
    """Validate untrusted image bytes and return their verified metadata."""

    limit = max_bytes if max_bytes is not None else settings.max_upload_mb * 1024 * 1024
    if declared_mime_type not in ALLOWED_MIME:
        raise ValidationError_("Este tipo de archivo no es compatible. Usa PNG, JPG o WebP.")
    if not content:
        raise ValidationError_("No pudimos procesar este archivo.")
    if len(content) > limit:
        raise ValidationError_(
            size_message
            or f"El archivo supera el tamaño permitido de {settings.max_upload_mb} MB."
        )
    metadata = read_image_metadata(content)
    if metadata is None or metadata.mime_type != declared_mime_type:
        raise ValidationError_("No pudimos procesar este archivo.")
    if metadata.width <= 0 or metadata.height <= 0:
        raise ValidationError_("No pudimos procesar este archivo.")
    if metadata.width * metadata.height > settings.max_upload_pixels:
        raise ValidationError_("La imagen supera el límite de dimensiones permitido.")
    if metadata.width * metadata.height > len(content) * settings.max_upload_expansion_ratio:
        raise ValidationError_("No pudimos procesar este archivo de forma segura.")
    return metadata


#: How far a returned frame may drift from the requested one. Providers round to
#: their own pixel grid, so an exact match is too strict; a different format is
#: not a rounding difference, and 2% cannot turn 9:16 into a square.
FRAME_TOLERANCE = 0.02


def enforce_expected_frame(
    metadata: ImageMetadata, *, width: int, height: int, tolerance: float = FRAME_TOLERANCE
) -> None:
    """Reject an image whose shape is not the shape that was requested.

    A job records the format the user approved. Storing a square answer under a
    ``9:16`` job would silently deliver something nobody confirmed, so the
    proportion is checked before the bytes are allowed anywhere near storage.
    """

    if width <= 0 or height <= 0:  # pragma: no cover - server-owned constants
        raise ValidationError_("No pudimos procesar este archivo.")
    expected = width / height
    actual = metadata.width / metadata.height
    if abs(actual - expected) > expected * tolerance:
        raise ValidationError_("La imagen recibida no coincide con el formato solicitado.")
