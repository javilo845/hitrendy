from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.models import Business
from app.core.capabilities import (
    Capability,
    CapabilityOutcome,
    CapabilityRegistry,
    get_runtime_capability_registry,
)
from app.core.config import settings
from app.core.errors import AppError, ConflictError
from app.trends.adapters import default_fake_sources
from app.trends.contracts import (
    SourceCandidate,
    SourceResultStatus,
    TrendSource,
    source_applies,
    valid_result,
)
from app.trends.factory import configured_trend_sources, record_source_outcome
from app.trends.models import (
    TrendEvidence,
    TrendItem,
    TrendItemEvidence,
    TrendRun,
    TrendRunEvidence,
    WorkspaceTrendRelevance,
)
from app.trends.scoring import RELEVANCE_VERSION, SCORING_VERSION, score, workspace_relevance

RUN_WINDOW = timedelta(days=1)
# A trend represents one ISO calendar week in UTC.  This keeps a Monday-Friday
# re-observation in the same stable seven-day grouping window.
OBSERVATION_WINDOW = timedelta(days=7)
OBSERVATION_WINDOW_VERSION = "utc-week-v1"
ABANDONED_PROCESSING_AFTER = timedelta(minutes=15)
FUTURE_TOLERANCE = timedelta(minutes=5)
EMPTY_RUN_MESSAGE = "Las fuentes consultadas no encontraron tendencias nuevas."
NO_APPLICABLE_SOURCES_MESSAGE = "No había fuentes aplicables para esta región o categoría."


def canonical_url(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return None
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _hash(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode()).hexdigest()


def _title(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", value.casefold())).strip()


def _region(value: str) -> str:
    return value.strip().upper()


def _category(value: str | None) -> str | None:
    """Normalize an optional category before it enters any stable identity."""

    return value.strip().casefold() if value is not None else None


def _daily_window(value: datetime) -> datetime:
    normalized = value.astimezone(UTC)
    return normalized.replace(hour=0, minute=0, second=0, microsecond=0)


def _utc(value: datetime, now: datetime) -> datetime | None:
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    normalized = value.astimezone(UTC)
    return normalized if normalized <= now + FUTURE_TOLERANCE else None


def _stored_utc(value: datetime) -> datetime:
    """Read a UTC database value, including SQLite's timezone-less test codec.

    Adapter input never uses this helper: naive external datetimes are rejected
    by ``_utc``. SQLite merely loses timezone metadata for a value that was
    already validated and persisted as UTC.
    """

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def observation_window(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    year, week, _ = normalized.isocalendar()
    return f"{OBSERVATION_WINDOW_VERSION}:{year}-W{week:02d}"


def fake_sources_enabled() -> bool:
    return settings.trend_analysis_enabled and settings.app_env in {"development", "test"}


class TrendService:
    def __init__(
        self,
        db: AsyncSession,
        sources: tuple[TrendSource, ...] | None = None,
        now: datetime | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.db, self.now = db, (now or datetime.now(UTC)).astimezone(UTC)
        # Explicit injected sources are reserved for deterministic tests.  The
        # production path never installs demo sources automatically.
        if sources is not None:
            raw_sources = sources
        else:
            raw_sources = configured_trend_sources(db, now=self.now)
            if not raw_sources and fake_sources_enabled():
                raw_sources = default_fake_sources()
        seen: set[str] = set()
        self.sources = tuple(
            source
            for source in sorted(raw_sources, key=lambda item: item.identifier)
            if not (source.identifier in seen or seen.add(source.identifier))
        )
        self.capability_registry = capability_registry or get_runtime_capability_registry()

    async def refresh(self, *, workspace_id: str, region: str, category: str | None) -> TrendRun:
        """Compatibility facade: one global collection plus private relevance."""

        run = await self.collect(region=region, category=category)
        await self.compute_workspace_relevance(workspace_id)
        await self.db.commit()
        return run

    async def collect(self, *, region: str, category: str | None) -> TrendRun:
        """Collect one global scope without inventing a workspace owner."""

        if not fake_sources_enabled() and (
            not self.sources or any(source.source_type == "demo" for source in self.sources)
        ):
            raise AppError(
                "CAPABILITY_UNAVAILABLE",
                "El análisis de tendencias no está disponible.",
                status_code=503,
            )
        region = _region(region)
        category = _category(category)
        # The daily scope is deliberately bounded: equivalent requests share
        # one global collection in a window, while tomorrow can collect anew.
        window_start = _daily_window(self.now)
        fingerprint = _hash(
            window_start.date().isoformat(),
            region.casefold(),
            category or "",
        )
        category_condition = (
            TrendRun.category.is_(None)
            if category is None
            else TrendRun.category == category
        )
        existing = await self.db.scalar(
            select(TrendRun)
            .where(
                TrendRun.window_start == window_start,
                TrendRun.region == region,
                category_condition,
            )
            .with_for_update()
        )
        if existing is not None and existing.status in {"completed", "partial"}:
            await self.db.commit()
            return existing
        if existing is not None and existing.status == "processing":
            started = _stored_utc(existing.started_at) if existing.started_at else None
            if started and started > self.now - ABANDONED_PROCESSING_AFTER:
                raise ConflictError(
                    "La recopilación equivalente sigue en proceso. Inténtalo nuevamente en un momento.",
                    retryable=True,
                )
        # A source that does not declare this region or category is skipped
        # before any work happens.  Skipping is represented only by absence:
        # it is not attempted, so it cannot succeed or fail in this run.
        applicable = tuple(
            source
            for source in self.sources
            if source_applies(source, region=region, category=category)
        )
        attempted = json.dumps([source.identifier for source in applicable])
        run = existing or TrendRun(
            fingerprint=fingerprint,
            window_start=window_start,
            region=region,
            category=category,
            status="processing",
            sources_attempted=attempted,
            started_at=self.now,
        )
        if existing is not None:
            run.status = "processing"
            run.started_at = self.now
            run.sources_attempted = attempted
            run.sources_succeeded = "[]"
            run.sources_failed = "[]"
            run.public_error = None
            run.finished_at = None
        else:
            self.db.add(run)
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                existing = await self.db.scalar(
                    select(TrendRun).where(
                        TrendRun.window_start == window_start,
                        TrendRun.region == region,
                        category_condition,
                    )
                )
                if existing is None:
                    raise
                return existing

        successful: set[str] = set()
        failed: set[str] = set()
        source_outcomes: dict[str, tuple[SourceResultStatus, datetime | None]] = {}
        failure_statuses: list[SourceResultStatus] = []
        quota_resets: list[datetime] = []
        candidates: list[tuple[str, SourceCandidate]] = []
        source_candidates: set[str] = set()
        for source in applicable:
            if not source.available:
                failed.add(source.identifier)
                failure_statuses.append(SourceResultStatus.ERROR)
                source_outcomes[source.identifier] = (SourceResultStatus.ERROR, None)
                continue
            fetch_failure: SourceResultStatus | None = None
            try:
                validated = valid_result(await source.fetch(region=region, category=category))
            except TimeoutError:
                validated = None
                fetch_failure = SourceResultStatus.TIMEOUT
            except Exception:
                validated = None
                fetch_failure = SourceResultStatus.ERROR
            if validated is None:
                failed.add(source.identifier)
                status = fetch_failure or SourceResultStatus.INVALID
                failure_statuses.append(status)
                source_outcomes[source.identifier] = (status, None)
            elif validated.result.status == SourceResultStatus.SUCCESS:
                source_candidates.add(source.identifier)
                candidates.extend((source.identifier, item) for item in validated.result.candidates)
                if validated.invalid_candidates:
                    failed.add(source.identifier)
                    failure_statuses.append(SourceResultStatus.INVALID)
                    source_outcomes[source.identifier] = (SourceResultStatus.INVALID, None)
            else:
                # A response with no usable evidence is not an effective
                # source success.  It remains auditable in attempted while
                # the final source status is mutually exclusive.
                failed.add(source.identifier)
                failure_statuses.append(validated.result.status)
                source_outcomes[source.identifier] = (
                    validated.result.status,
                    validated.result.next_reset_at,
                )
                if validated.result.next_reset_at is not None:
                    quota_resets.append(validated.result.next_reset_at)

        evidence_sources: set[str] = set()
        invalid_sources: set[str] = set()
        for source, candidate in sorted(candidates, key=lambda item: (item[0], _title(item[1].title))):
            has_evidence, invalid = await self._publish_candidate(
                run, source, candidate, region, category
            )
            if has_evidence:
                evidence_sources.add(source)
            if invalid:
                invalid_sources.add(source)
        for source in source_candidates:
            if source not in evidence_sources or source in invalid_sources:
                failed.add(source)
                failure_statuses.append(SourceResultStatus.INVALID)
                source_outcomes[source] = (SourceResultStatus.INVALID, None)
            else:
                successful.add(source)
        successful.difference_update(failed)
        for source in successful:
            source_outcomes[source] = (SourceResultStatus.SUCCESS, None)
        for source, (status, reset) in source_outcomes.items():
            await record_source_outcome(source, status, reset)
        successful_ordered, failed_ordered = sorted(successful), sorted(failed)
        run.sources_succeeded, run.sources_failed = (
            json.dumps(successful_ordered), json.dumps(failed_ordered)
        )
        has_valid_evidence = bool(evidence_sources)
        run.status = (
            "completed"
            if has_valid_evidence and not failed_ordered
            else "partial"
            if has_valid_evidence
            else "failed"
        )
        if failed_ordered and has_valid_evidence:
            run.public_error = "Algunas fuentes no estuvieron disponibles."
        elif not has_valid_evidence and not applicable:
            run.public_error = NO_APPLICABLE_SOURCES_MESSAGE
        elif (
            not has_valid_evidence
            and failure_statuses
            and all(status == SourceResultStatus.EMPTY for status in failure_statuses)
        ):
            run.public_error = EMPTY_RUN_MESSAGE
        else:
            run.public_error = (
                "No se pudo obtener evidencia de tendencias."
                if not has_valid_evidence
                else None
            )
        run.finished_at = self.now
        await self.db.commit()
        # An empty applicable set is not a provider outcome: no provider was
        # attempted, so the prior global capability health must remain intact.
        if applicable:
            await self._record_capability_outcome(
                run.status, failure_statuses, min(quota_resets) if quota_resets else None
            )
        return run

    async def _record_capability_outcome(
        self,
        run_status: str,
        failures: list[SourceResultStatus],
        next_reset_at: datetime | None = None,
    ) -> None:
        if run_status == "completed":
            outcome = CapabilityOutcome.SUCCESS
        elif run_status == "partial":
            outcome = (
                CapabilityOutcome.TIMEOUT
                if SourceResultStatus.TIMEOUT in failures
                else CapabilityOutcome.INVALID_RESPONSE
            )
        elif SourceResultStatus.QUOTA_EXHAUSTED in failures:
            outcome = CapabilityOutcome.QUOTA_EXHAUSTED
        elif SourceResultStatus.RATE_LIMITED in failures:
            outcome = CapabilityOutcome.RATE_LIMITED
        elif SourceResultStatus.TIMEOUT in failures:
            outcome = CapabilityOutcome.TIMEOUT
        elif SourceResultStatus.INVALID in failures:
            outcome = CapabilityOutcome.INVALID_RESPONSE
        else:
            outcome = CapabilityOutcome.PROVIDER_ERROR
        await self.capability_registry.record_outcome_for(
            Capability.TREND_ANALYSIS, outcome, next_reset_at
        )

    async def _publish_candidate(
        self,
        run: TrendRun,
        source: str,
        candidate: SourceCandidate,
        requested_region: str,
        requested_category: str | None,
    ) -> tuple[bool, bool]:
        candidate_observed = _utc(candidate.observed_at, self.now)
        candidate_region = _region(candidate.region)
        normalized_category = _category(candidate.category)
        normalized_title = _title(candidate.title)
        if (
            not normalized_title
            or not candidate_region
            or candidate_observed is None
            or candidate_region != requested_region
            or (
                requested_category is not None
                and normalized_category != requested_category
            )
        ):
            return False, True
        candidate_window = observation_window(candidate_observed)
        valid = []
        invalid = False
        for evidence in candidate.evidence:
            observed = _utc(evidence.observed_at, self.now)
            url = canonical_url(evidence.source_url)
            if (
                url
                and evidence.region.strip()
                and observed is not None
                and 0 <= evidence.confidence <= 1
                and _region(evidence.region) == candidate_region
                and observation_window(observed) == candidate_window
            ):
                valid.append((evidence, url, observed))
            else:
                invalid = True
        if not valid:
            return False, True  # central no-evidence rule
        item_window = candidate_window
        group_key = _hash(
            normalized_title,
            candidate_region,
            normalized_category or "",
            item_window,
        )
        item = await self.db.scalar(select(TrendItem).where(TrendItem.group_key == group_key))
        if item is None:
            components, total = score(
                observed_at=candidate_observed,
                evidence_count=len(valid),
                source_count=1,
                now=self.now,
            )
            item = TrendItem(
                group_key=group_key,
                observation_window=item_window,
                fingerprint=_hash(group_key, item_window),
                title=candidate.title,
                summary=candidate.summary,
                region=candidate_region,
                category=normalized_category,
                observed_at=candidate_observed,
                freshness_score=components["freshness"],
                scoring_version=SCORING_VERSION,
                component_scores=json.dumps(components, sort_keys=True),
                total_score=total,
                calculated_at=self.now,
            )
            self.db.add(item)
            await self.db.flush()
        for evidence, url, observed in valid:
            evidence_window = observation_window(observed)
            fingerprint = _hash(source, url, _region(evidence.region), evidence_window)
            trend_evidence = await self.db.scalar(
                select(TrendEvidence).where(TrendEvidence.evidence_fingerprint == fingerprint)
            )
            if trend_evidence is None:
                trend_evidence = TrendEvidence(
                    source=source,
                    source_url=evidence.source_url,
                    canonical_url=url,
                    observed_at=observed,
                    region=_region(evidence.region),
                    observation_window=evidence_window,
                    confidence=evidence.confidence,
                    evidence_fingerprint=fingerprint,
                )
                self.db.add(trend_evidence)
                await self.db.flush()
            else:
                # A canonical observation is unique in a UTC window.  Later
                # observations refine its freshness without duplicating it;
                # confidence follows a deterministic best-observed policy.
                if observed > _stored_utc(trend_evidence.observed_at):
                    trend_evidence.observed_at = observed
                trend_evidence.confidence = max(
                    float(trend_evidence.confidence), float(evidence.confidence)
                )
            item_evidence = await self.db.get(
                TrendItemEvidence,
                {"trend_item_id": item.id, "trend_evidence_id": trend_evidence.id},
            )
            if item_evidence is None:
                self.db.add(
                    TrendItemEvidence(
                        trend_item_id=item.id, trend_evidence_id=trend_evidence.id
                    )
                )
            association = await self.db.get(
                TrendRunEvidence, {"trend_run_id": run.id, "trend_evidence_id": trend_evidence.id}
            )
            if association is None:
                self.db.add(TrendRunEvidence(trend_run_id=run.id, trend_evidence_id=trend_evidence.id))
        evidences = (
            await self.db.scalars(
                select(TrendEvidence)
                .join(TrendItemEvidence)
                .where(TrendItemEvidence.trend_item_id == item.id)
            )
        ).all()
        if not evidences:
            return False, True
        item.observed_at = max(_stored_utc(evidence.observed_at) for evidence in evidences)
        components, total = score(
            observed_at=item.observed_at,
            evidence_count=len(evidences),
            source_count=len({e.source for e in evidences}),
            now=self.now,
        )
        item.freshness_score, item.component_scores, item.total_score, item.calculated_at = (
            components["freshness"], json.dumps(components, sort_keys=True), total, self.now
        )
        return True, invalid

    async def compute_workspace_relevance(self, workspace_id: str) -> None:
        """Recalculate private relevance using persisted global evidence only."""

        business = await self.db.scalar(
            select(Business).where(Business.workspace_id == workspace_id).order_by(Business.created_at)
        )
        if business is None:
            return
        items = (await self.db.scalars(select(TrendItem))).all()
        for item in items:
            components, total = workspace_relevance(
                trend_category=item.category, region=item.region, business=business
            )
            relevance = await self.db.scalar(
                select(WorkspaceTrendRelevance).where(
                    WorkspaceTrendRelevance.workspace_id == workspace_id,
                    WorkspaceTrendRelevance.trend_item_id == item.id,
                )
            )
            if relevance is None:
                self.db.add(WorkspaceTrendRelevance(
                    workspace_id=workspace_id, trend_item_id=item.id, score=total,
                    relevance_version=RELEVANCE_VERSION,
                    component_scores=json.dumps(components, sort_keys=True), calculated_at=self.now,
                ))
            else:
                relevance.score, relevance.relevance_version, relevance.component_scores, relevance.calculated_at = (
                    total, RELEVANCE_VERSION, json.dumps(components, sort_keys=True), self.now
                )

    async def latest_run(
        self,
        *,
        region: str,
        category: str | None,
    ) -> TrendRun | None:
        return await self.db.scalar(
            select(TrendRun)
            .where(
                TrendRun.region == _region(region),
                TrendRun.category == _category(category),
            )
            .order_by(TrendRun.window_start.desc(), TrendRun.started_at.desc(), TrendRun.id)
            .limit(1)
        )

    async def latest_successful_run(
        self,
        *,
        region: str,
        category: str | None,
    ) -> TrendRun | None:
        return await self.db.scalar(
            select(TrendRun)
            .where(
                TrendRun.region == _region(region),
                TrendRun.category == _category(category),
                TrendRun.status.in_(("completed", "partial")),
            )
            .order_by(TrendRun.window_start.desc(), TrendRun.finished_at.desc(), TrendRun.id)
            .limit(1)
        )

    async def manual_refresh_availability(
        self,
        *,
        region: str,
        category: str | None,
    ) -> tuple[bool, datetime | None, TrendRun | None]:
        """Return the global scope cooldown without touching providers or quota."""

        run = await self.latest_run(region=region, category=category)
        if run is None:
            return True, None, None
        started_at = _stored_utc(run.started_at)
        if run.status == "processing" and started_at > self.now - ABANDONED_PROCESSING_AFTER:
            return False, started_at + ABANDONED_PROCESSING_AFTER, run
        if run.status not in {"completed", "partial"} or run.finished_at is None:
            return True, None, run
        finished_at = _stored_utc(run.finished_at)
        next_window = datetime.combine(
            finished_at.date() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=UTC,
        )
        next_refresh_at = max(
            finished_at + timedelta(seconds=settings.trends_manual_cooldown_seconds),
            next_window,
        )
        return self.now >= next_refresh_at, next_refresh_at, run

    async def list(
        self,
        *,
        workspace_id: str,
        region: str | None,
        category: str | None,
        limit: int,
        private_ranked: bool = False,
    ) -> list[TrendItem]:
        """List visible items with a deterministic public or Home ranking.

        Home opts into private ranking: workspace relevance DESC, global score
        DESC, then trend ID. Other callers retain the established global-first
        order.
        """

        statement = select(TrendItem).join(WorkspaceTrendRelevance).where(
            WorkspaceTrendRelevance.workspace_id == workspace_id
        )
        if region:
            statement = statement.where(TrendItem.region == region)
        if category:
            statement = statement.where(TrendItem.category == category)
        ordering = (
            (
                WorkspaceTrendRelevance.score.desc(),
                TrendItem.total_score.desc(),
                TrendItem.id,
            )
            if private_ranked
            else (
                TrendItem.total_score.desc(),
                WorkspaceTrendRelevance.score.desc(),
                TrendItem.id,
            )
        )
        return list(
            (
                await self.db.scalars(
                    statement.order_by(*ordering).limit(limit)
                )
            ).all()
        )

    async def detail(self, *, workspace_id: str, trend_id: str) -> TrendItem | None:
        return await self.db.scalar(select(TrendItem).join(WorkspaceTrendRelevance).where(
            TrendItem.id == trend_id, WorkspaceTrendRelevance.workspace_id == workspace_id
        ))
