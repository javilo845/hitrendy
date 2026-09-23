from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

from app.core.config import settings

logger = logging.getLogger("hitrendy.monitoring")


@dataclass
class MetricsSnapshot:
    requests_total: int
    responses_by_status: dict[str, int]
    errors_total: int
    duration_ms_total: float
    alerts: list[str]


@dataclass
class MetricsRegistry:
    """Small process-local registry with a stable Prometheus-compatible view.

    Durable product usage and billing live in PostgreSQL. This registry is only
    operational telemetry; losing it on a restart is expected and safe.
    """

    _lock: Lock = field(default_factory=Lock)
    _requests_total: int = 0
    _errors_total: int = 0
    _duration_ms_total: float = 0.0
    _responses: Counter[str] = field(default_factory=Counter)
    _error_codes: Counter[str] = field(default_factory=Counter)

    def record_request(self, *, status_code: int, duration_ms: float, error_code: str | None = None) -> None:
        with self._lock:
            self._requests_total += 1
            self._duration_ms_total += max(duration_ms, 0.0)
            self._responses[str(status_code)] += 1
            if status_code >= 500:
                self._errors_total += 1
            if error_code:
                self._error_codes[error_code] += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            requests = self._requests_total
            errors = self._errors_total
            responses = dict(self._responses)
            error_codes = dict(self._error_codes)
            duration = self._duration_ms_total
        error_rate = (errors / requests * 100) if requests else 0.0
        alerts: list[str] = []
        if requests and error_rate >= settings.alert_error_rate_percent:
            alerts.append("error_rate_high")
        return MetricsSnapshot(
            requests_total=requests,
            responses_by_status=responses | {f"error_code:{key}": value for key, value in error_codes.items()},
            errors_total=errors,
            duration_ms_total=duration,
            alerts=alerts,
        )

    def prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP hitrendy_http_requests_total Total HTTP requests handled by this process.",
            "# TYPE hitrendy_http_requests_total counter",
            f"hitrendy_http_requests_total {snapshot.requests_total}",
            "# HELP hitrendy_http_errors_total HTTP 5xx responses handled by this process.",
            "# TYPE hitrendy_http_errors_total counter",
            f"hitrendy_http_errors_total {snapshot.errors_total}",
            "# HELP hitrendy_http_error_rate_percent Current process 5xx rate.",
            "# TYPE hitrendy_http_error_rate_percent gauge",
            f"hitrendy_http_error_rate_percent {(snapshot.errors_total / snapshot.requests_total * 100) if snapshot.requests_total else 0.0:.2f}",
            "# HELP hitrendy_http_duration_ms_total Sum of request durations in milliseconds.",
            "# TYPE hitrendy_http_duration_ms_total counter",
            f"hitrendy_http_duration_ms_total {snapshot.duration_ms_total:.2f}",
        ]
        for status, count in sorted(snapshot.responses_by_status.items()):
            if status.startswith("error_code:"):
                lines.append(
                    f'hitrendy_http_errors_by_code_total{{code="{status.removeprefix("error_code:")}"}} {count}'
                )
            else:
                lines.append(f'hitrendy_http_responses_total{{status="{status}"}} {count}')
        for alert in snapshot.alerts:
            lines.append(f'hitrendy_alert{{name="{alert}"}} 1')
        return "\n".join(lines) + "\n"


class ErrorTracker:
    def capture(self, *, request_id: str, path: str, error_type: str) -> None:
        raise NotImplementedError


class DisabledErrorTracker(ErrorTracker):
    def capture(self, *, request_id: str, path: str, error_type: str) -> None:
        del request_id, path, error_type


class LoggingErrorTracker(ErrorTracker):
    def capture(self, *, request_id: str, path: str, error_type: str) -> None:
        logger.error(
            "error_tracking_event",
            extra={"request_id": request_id, "path": path, "error_type": error_type},
        )


metrics = MetricsRegistry()


def get_error_tracker() -> ErrorTracker:
    if settings.error_tracking_provider == "disabled":
        return DisabledErrorTracker()
    # Sentry integration remains behind the same interface until the beta has a
    # deployment-owned DSN. Logging is still useful and never sends user data.
    return LoggingErrorTracker()
