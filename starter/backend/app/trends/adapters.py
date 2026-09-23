from __future__ import annotations

from datetime import UTC, datetime

from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult


class FakeTrendSource:
    """Deterministic demo-only adapter; it never contacts a network service."""

    source_type = "demo"
    supported_regions = ("HN", "GLOBAL")
    supported_categories: tuple[str, ...] = ()
    available = True

    def __init__(self, identifier: str, mode: str = "success") -> None:
        self.identifier = identifier
        self.public_name = f"Fuente demo: {identifier}"
        self.mode = mode

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        if self.mode == "empty":
            return SourceFetchResult("empty")
        if self.mode in {"timeout", "error", "invalid"}:
            return SourceFetchResult(
                self.mode, public_error="La fuente demo no pudo completar la consulta."
            )
        observed = datetime(2026, 1, 15, 12, tzinfo=UTC)
        topic = "Interés por contenido local útil"
        url = "https://demo.hitrendy.invalid/evidence/local-content"
        if self.mode == "duplicate":
            candidates = (
                SourceCandidate(
                    topic,
                    "Señal demo verificable.",
                    region,
                    category,
                    observed,
                    (SourceEvidence(url, observed, region, 0.8),),
                ),
            ) * 2
        else:
            suffix = "community" if self.identifier.endswith("community") else "catalog"
            candidates = (
                SourceCandidate(
                    topic,
                    "Señal demo verificable.",
                    region,
                    category,
                    observed,
                    (SourceEvidence(f"{url}?source={suffix}", observed, region, 0.8),),
                ),
            )
        return SourceFetchResult("success", candidates)


def default_fake_sources() -> tuple[FakeTrendSource, ...]:
    return (FakeTrendSource("demo-catalog"), FakeTrendSource("demo-community"))
