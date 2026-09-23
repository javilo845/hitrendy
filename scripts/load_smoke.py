#!/usr/bin/env python3
"""Bounded read-only smoke load for a staging instance."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request(url: str) -> int:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-supplied staging URL
            response.read(1024)
            return response.status
    except HTTPError as exc:
        return exc.code
    except URLError:
        return 0


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga pequeña y sólo lectura para beta HiTrendy")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args(argv)
    if not 1 <= args.requests <= 100 or not 1 <= args.concurrency <= 10:
        parser.error("--requests debe estar entre 1 y 100; --concurrency entre 1 y 10")

    base_url = args.base_url.rstrip("/")
    urls = [f"{base_url}/health/live" if index % 2 == 0 else f"{base_url}/api/v1/policies" for index in range(args.requests)]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        statuses = list(executor.map(_request, urls))

    success = sum(status == 200 for status in statuses)
    print(f"Carga de lectura: {success}/{len(statuses)} respuestas HTTP 200")
    if success != len(statuses):
        print(f"Estados observados: {sorted(set(statuses))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
