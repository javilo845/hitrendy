"""Cron-style entrypoint for daily trend collection.

Example:

    python -m app.trends.worker run-due

This module intentionally has no forever loop. A hosting scheduler or cron
invokes it, and durable database state makes repeated invocations safe.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.trends.jobs import run_due


async def _main(args: argparse.Namespace) -> int:
    if args.command != "run-due":
        return 2
    result = await run_due()
    logging.getLogger("hitrendy.trends.worker").info(
        "trend_run_due_completed scopes=%s failed=%s workspaces_scored=%s",
        len(result.scopes),
        result.failed,
        result.workspaces_scored,
    )
    return 1 if result.failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Jobs externos de tendencias HiTrendy")
    parser.add_argument("command", choices=("run-due",))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
