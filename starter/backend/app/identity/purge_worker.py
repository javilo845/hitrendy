"""Standalone account purge worker.

Run it as its own process, never inside a web instance:

    python -m app.identity.purge_worker --interval 30

Several replicas can run at the same time: jobs are claimed with
``SELECT ... FOR UPDATE SKIP LOCKED`` so a job is never processed twice.
Use ``--once`` in cron-style deployments or in scripts. The worker performs no
migrations; the schema must already be at head.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal

from app.db.session import get_session_factory
from app.identity.purge import process_available_purge_jobs, recover_stuck_jobs

logger = logging.getLogger("hitrendy.purge.worker")

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_BATCH = 25


async def run_once(*, batch: int = DEFAULT_BATCH) -> int:
    """Recover abandoned jobs and process everything currently claimable."""

    session_factory = get_session_factory()
    async with session_factory() as db:
        recovered = await recover_stuck_jobs(db)
        if recovered:
            logger.info("purge_worker_recovered count=%s", recovered)
        processed = await process_available_purge_jobs(db, limit=batch)
    if processed:
        logger.info("purge_worker_processed count=%s", processed)
    return processed


async def run_forever(*, interval: float, batch: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await run_once(batch=batch)
        except Exception:
            # Never log the exception payload: it can carry provider secrets.
            logger.warning("purge_worker_cycle_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


async def _main(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        await run_once(batch=args.batch)
        return 0
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(getattr(signal, signal_name), stop.set)
    logger.info("purge_worker_started interval=%s batch=%s", args.interval, args.batch)
    await run_forever(interval=args.interval, batch=args.batch, stop=stop)
    logger.info("purge_worker_stopped")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker durable de purga de cuentas HiTrendy")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--once", action="store_true", help="Procesa un ciclo y termina")
    args = parser.parse_args()
    import sys
    if sys.platform == "win32":
        import selectors
        raise SystemExit(asyncio.run(_main(args), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())))
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
