"""Pure-Python ISO-BMFF validation for untrusted video bytes."""

from __future__ import annotations

import struct
from dataclasses import dataclass

ALLOWED_VIDEO_MIME = {"video/mp4"}
ALLOWED_BRANDS = {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V "}
ALLOWED_VIDEO_CODECS = {b"avc1", b"avc3"}
RATIO_TOLERANCE = 0.02
DURATION_TOLERANCE_SECONDS = 1.0
MAX_VIDEO_DIMENSION = 4_096
MAX_CONTAINER_DEPTH = 8
MAX_BOXES = 4_096
CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf"}


class VideoValidationError(ValueError):
    """Safe validation failure with a stable, non-provider-facing code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    mime_type: str
    extension: str
    width: int
    height: int
    duration_seconds: float
    size_bytes: int


@dataclass
class _WalkState:
    boxes: int = 0


def _invalid_container(
    message: str = "El contenedor de video no es válido.",
) -> VideoValidationError:
    return VideoValidationError("invalid_container", message)


def _walk(
    data: bytes,
    start: int,
    end: int,
    depth: int = 0,
    _state: _WalkState | None = None,
):
    """Yield ISO-BMFF boxes while bounding recursion and total work."""

    if depth > MAX_CONTAINER_DEPTH:
        raise _invalid_container("La profundidad del contenedor de video excede el límite.")
    state = _state or _WalkState()
    if start < 0 or end < start or end > len(data):
        raise _invalid_container()

    offset = start
    while offset + 8 <= end:
        if state.boxes >= MAX_BOXES:
            raise _invalid_container("El contenedor de video contiene demasiadas cajas.")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        header = 8
        if size == 1:
            if offset + 16 > end:
                raise _invalid_container()
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = end - offset
        if size < header or offset + size > end:
            raise _invalid_container()
        state.boxes += 1
        yield kind, offset + header, offset + size, depth
        if kind in CONTAINER_BOXES:
            yield from _walk(data, offset + header, offset + size, depth + 1, state)
        offset += size
    if offset != end:
        raise _invalid_container("El contenedor de video está truncado.")


def _read_movie_duration(data: bytes, boxes: list[tuple[bytes, int, int, int]]) -> float:
    if not any(kind == b"moov" for kind, _, _, _ in boxes):
        raise _invalid_container("Falta la caja moov del video.")
    movie_headers = [(body, end) for kind, body, end, _ in boxes if kind == b"mvhd"]
    if not movie_headers:
        raise VideoValidationError("invalid_duration", "Falta la duración del video.")
    body, end = movie_headers[0]
    if end - body < 4:
        raise VideoValidationError("invalid_duration", "La duración del video no es válida.")
    version = data[body]
    try:
        if version == 1:
            if end - body < 32:
                raise VideoValidationError(
                    "invalid_duration", "La duración del video no es válida."
                )
            timescale = struct.unpack_from(">I", data, body + 20)[0]
            duration = struct.unpack_from(">Q", data, body + 24)[0]
        elif version == 0:
            if end - body < 20:
                raise VideoValidationError(
                    "invalid_duration", "La duración del video no es válida."
                )
            timescale = struct.unpack_from(">I", data, body + 12)[0]
            duration = struct.unpack_from(">I", data, body + 16)[0]
        else:
            raise VideoValidationError("invalid_duration", "La versión de duración no es válida.")
    except struct.error as exc:
        raise VideoValidationError(
            "invalid_duration", "La duración del video no es válida."
        ) from exc
    if timescale <= 0 or duration <= 0:
        raise VideoValidationError("invalid_duration", "La duración del video no es válida.")
    return duration / timescale


def _video_track(data: bytes, boxes: list[tuple[bytes, int, int, int]]) -> tuple[int, int]:
    """Return the bounds of a track with an allowlisted H.264 video sample entry."""

    tracks = [(body, end) for kind, body, end, _ in boxes if kind == b"trak"]
    for track_body, track_end in tracks:
        handler_types: list[bytes] = []
        codecs: list[bytes] = []
        for kind, body, end, _ in boxes:
            if not track_body <= body < end <= track_end:
                continue
            if kind == b"hdlr":
                if end - body < 12:
                    raise VideoValidationError(
                        "invalid_track", "La pista de video no tiene un handler válido."
                    )
                handler_types.append(data[body + 8 : body + 12])
            elif kind == b"stsd":
                if end - body < 8:
                    raise VideoValidationError(
                        "invalid_codec", "La pista de video no tiene una descripción válida."
                    )
                entry_count = struct.unpack_from(">I", data, body + 4)[0]
                entry_offset = body + 8
                for _ in range(min(entry_count, 32)):
                    if entry_offset + 8 > end:
                        raise VideoValidationError(
                            "invalid_codec", "La descripción del codec está truncada."
                        )
                    entry_size = struct.unpack_from(">I", data, entry_offset)[0]
                    if entry_size < 8 or entry_offset + entry_size > end:
                        raise VideoValidationError(
                            "invalid_codec", "La descripción del codec no es válida."
                        )
                    codecs.append(data[entry_offset + 4 : entry_offset + 8])
                    entry_offset += entry_size
        if b"vide" in handler_types and set(codecs).intersection(ALLOWED_VIDEO_CODECS):
            return track_body, track_end
        if b"vide" in handler_types:
            raise VideoValidationError("codec_not_allowed", "El codec del video no está permitido.")
    raise VideoValidationError(
        "invalid_track", "El resultado no contiene una pista de video reproducible."
    )


def _read_dimensions(
    data: bytes,
    boxes: list[tuple[bytes, int, int, int]],
    track: tuple[int, int],
) -> tuple[int, int]:
    track_body, track_end = track
    for kind, body, end, _ in boxes:
        if not track_body <= body < end <= track_end or kind != b"tkhd" or end - body < 8:
            continue
        try:
            width_fixed, height_fixed = struct.unpack_from(">II", data, end - 8)
        except struct.error as exc:
            raise VideoValidationError(
                "invalid_dimensions", "Las dimensiones del video no son válidas."
            ) from exc
        width = int(width_fixed / 65_536)
        height = int(height_fixed / 65_536)
        if 0 < width <= MAX_VIDEO_DIMENSION and 0 < height <= MAX_VIDEO_DIMENSION:
            return width, height
        raise VideoValidationError(
            "invalid_dimensions", "Las dimensiones del video exceden el límite permitido."
        )
    raise VideoValidationError("invalid_dimensions", "Faltan dimensiones válidas del video.")


def _validate_ftyp(data: bytes, boxes: list[tuple[bytes, int, int, int]]) -> None:
    ftyp_boxes = [(body, end) for kind, body, end, _ in boxes if kind == b"ftyp"]
    if not ftyp_boxes:
        raise _invalid_container("Falta la marca ftyp del video.")
    body, end = ftyp_boxes[0]
    if end - body < 8 or (end - body - 8) % 4:
        raise _invalid_container("La marca ftyp del video no es válida.")
    major_brand = data[body : body + 4]
    compatible_brands = {data[offset : offset + 4] for offset in range(body + 8, end, 4)}
    if major_brand not in ALLOWED_BRANDS and not compatible_brands.intersection(ALLOWED_BRANDS):
        raise _invalid_container("La marca del video no está permitida.")


def validate_video_bytes(
    content: bytes,
    *,
    declared_mime: str,
    expected_duration: float,
    expected_ratio: float,
    max_bytes: int,
) -> VideoMetadata:
    """Validate an MP4 container, duration and vertical frame dimensions."""

    if not content:
        raise VideoValidationError("empty_response", "El proveedor no devolvió contenido.")
    if len(content) > max_bytes:
        raise VideoValidationError("too_large", "El video supera el tamaño permitido.")
    if declared_mime not in ALLOWED_VIDEO_MIME:
        raise _invalid_container("El tipo de video no está permitido.")
    if expected_duration <= 0:
        raise VideoValidationError("invalid_duration", "La duración esperada no es válida.")
    if expected_ratio <= 0:
        raise VideoValidationError("invalid_ratio", "La proporción esperada no es válida.")

    try:
        boxes = list(_walk(content, 0, len(content)))
    except (struct.error, IndexError) as exc:
        raise _invalid_container() from exc
    top_level = {(kind, body, end) for kind, body, end, depth in boxes if depth == 0}
    if not any(kind == b"ftyp" for kind, _, _ in top_level):
        raise _invalid_container("Falta la caja ftyp del video.")
    if not any(kind == b"moov" for kind, _, _ in top_level):
        raise _invalid_container("Falta la caja moov del video.")
    mdat_boxes = [(body, end) for kind, body, end, depth in boxes if depth == 0 and kind == b"mdat"]
    if not mdat_boxes or not any(end > body for body, end in mdat_boxes):
        raise _invalid_container("Falta contenido de video en la caja mdat.")
    _validate_ftyp(content, boxes)
    duration = _read_movie_duration(content, boxes)
    if abs(duration - expected_duration) > DURATION_TOLERANCE_SECONDS:
        raise VideoValidationError("invalid_duration", "La duración del video no coincide.")
    video_track = _video_track(content, boxes)
    width, height = _read_dimensions(content, boxes, video_track)
    if abs((width / height) - expected_ratio) > RATIO_TOLERANCE:
        raise VideoValidationError("invalid_ratio", "La proporción del video no coincide.")
    return VideoMetadata(
        mime_type="video/mp4",
        extension=".mp4",
        width=width,
        height=height,
        duration_seconds=duration,
        size_bytes=len(content),
    )
