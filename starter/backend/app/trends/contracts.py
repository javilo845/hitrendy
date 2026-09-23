from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Protocol


class SourceResultStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    ERROR = "error"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"


@dataclass(frozen=True)
class SourceEvidence:
    source_url: str
    observed_at: datetime
    region: str
    confidence: float = 0.5


@dataclass(frozen=True)
class SourceCandidate:
    title: str
    summary: str
    region: str
    category: str | None
    observed_at: datetime
    evidence: tuple[SourceEvidence, ...]


@dataclass(frozen=True)
class SourceFetchResult:
    status: SourceResultStatus | str
    candidates: tuple[SourceCandidate, ...] = ()
    public_error: str | None = None
    next_reset_at: datetime | None = None


class TrendSource(Protocol):
    identifier: str
    public_name: str
    source_type: str
    supported_regions: tuple[str, ...]
    # An empty tuple declares a source that serves every category.
    supported_categories: tuple[str, ...] = ()
    available: bool

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult: ...


def source_applies(source: TrendSource, *, region: str, category: str | None) -> bool:
    """Report whether a source declares coverage for this region and category.

    A source outside its declared scope is not broken: it is simply not
    applicable.  The caller skips it entirely, so it is never fetched, never
    recorded as an outcome and never counted as a provider failure.
    """

    regions = {
        item.strip().upper()
        for item in source.supported_regions
        if isinstance(item, str) and item.strip()
    }
    if region.strip().upper() not in regions:
        return False
    categories = {
        item.strip().casefold()
        for item in getattr(source, "supported_categories", ())
        if isinstance(item, str) and item.strip()
    }
    return not categories or not category or category.strip().casefold() in categories


@dataclass(frozen=True)
class ValidatedSourceResult:
    result: SourceFetchResult
    invalid_candidates: bool = False


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _valid_candidate(candidate: object) -> bool:
    if not isinstance(candidate, SourceCandidate):
        return False
    if not isinstance(candidate.title, str) or not candidate.title.strip():
        return False
    if not isinstance(candidate.summary, str):
        return False
    if not isinstance(candidate.region, str) or not candidate.region.strip():
        return False
    if candidate.category is not None and not isinstance(candidate.category, str):
        return False
    if not _aware(candidate.observed_at) or not isinstance(candidate.evidence, (tuple, list)):
        return False
    for evidence in candidate.evidence:
        if not isinstance(evidence, SourceEvidence):
            return False
        if not isinstance(evidence.source_url, str):
            return False
        if not _aware(evidence.observed_at) or not isinstance(evidence.region, str) or not evidence.region.strip():
            return False
        if (
            not isinstance(evidence.confidence, (int, float))
            or isinstance(evidence.confidence, bool)
            or not isfinite(float(evidence.confidence))
            or not 0 <= float(evidence.confidence) <= 1
        ):
            return False
    return True


def valid_result(result: object) -> ValidatedSourceResult | None:
    """Validate and sanitize adapter output without retaining invalid payload data.

    Invalid candidates are discarded individually.  The caller records the
    source as degraded while still publishing its independently valid signals.
    """

    if not isinstance(result, SourceFetchResult):
        return None
    try:
        status = SourceResultStatus(result.status)
    except ValueError:
        return None
    if not isinstance(result.candidates, (tuple, list)):
        return None
    next_reset_at = result.next_reset_at if _aware(result.next_reset_at) else None
    candidates = tuple(result.candidates)
    if status == SourceResultStatus.EMPTY:
        return (
            ValidatedSourceResult(SourceFetchResult(status=status, next_reset_at=next_reset_at))
            if not candidates
            else None
        )
    if status != SourceResultStatus.SUCCESS:
        return ValidatedSourceResult(SourceFetchResult(status=status, next_reset_at=next_reset_at))
    valid = tuple(candidate for candidate in candidates if _valid_candidate(candidate))
    invalid = len(valid) != len(candidates)
    if not valid and candidates:
        return ValidatedSourceResult(SourceFetchResult(status=SourceResultStatus.INVALID), True)
    return ValidatedSourceResult(
        SourceFetchResult(status=SourceResultStatus.SUCCESS, candidates=valid), invalid
    )
