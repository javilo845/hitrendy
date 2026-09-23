#!/usr/bin/env python3
"""Run the non-destructive staging checks required before a beta session."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(url: str) -> tuple[int, str]:
    request = Request(url, headers={"Accept": "application/json, text/plain"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-supplied staging URL
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"no se pudo conectar con {url}: {exc.reason}") from exc


def _json(text: str) -> dict[str, object]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError("la respuesta no es un objeto JSON")
    return value


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Checklist de readiness de beta HiTrendy")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    checks = (
        ("live", "/health/live"),
        ("ready", "/health/ready"),
        ("policies", "/api/v1/policies"),
        ("metrics", "/health/metrics"),
    )

    failed = False
    for name, path in checks:
        try:
            status, body = _get(f"{base_url}{path}")
            if name == "policies":
                payload = _json(body)
                required = {"privacy", "terms", "support", "email_verification", "closed_beta"}
                ok = status == 200 and required <= payload.keys()
            elif name == "metrics":
                ok = status == 200 and "hitrendy_http_requests_total" in body
            else:
                ok = status == 200
            print(f"{'OK' if ok else 'FAIL'} {name}: HTTP {status}")
            failed = failed or not ok
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"FAIL {name}: {exc}")
            failed = True

    if failed:
        print("Readiness de beta no aprobado.", file=sys.stderr)
        return 1
    print("Readiness de beta aprobado; falta ejecutar el checklist de usuario real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
