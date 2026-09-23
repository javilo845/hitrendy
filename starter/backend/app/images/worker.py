"""Standalone image generation worker.

Run it as its own process, never inside a web instance:

    python -m app.images.worker --interval 5

Several replicas can run at the same time: jobs are claimed with
``SELECT ... FOR UPDATE SKIP LOCKED`` so a paid generation is never issued
twice for the same job. Use ``--once`` in cron-style deployments or in
scripts. The worker performs no migrations; the schema must already be at head.

A durable job survives a restart: the HTTP request that confirmed it is long
gone by the time the provider is called, which is exactly why the request
handler never does the work itself.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys

if sys.platform.startswith("win"):
    with contextlib.suppress(Exception):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db import registry as _registry  # noqa: F401  # maps every table before any query
from app.db.session import get_session_factory
from app.images.service import claim_next_job, execute_job

logger = logging.getLogger("hitrendy.images.worker")

DEFAULT_INTERVAL_SECONDS = 5
DEFAULT_BATCH = 5


async def run_once(*, batch: int = DEFAULT_BATCH) -> int:
    """Claim and execute up to ``batch`` jobs, one session per job.

    Each job gets its own session and its own transaction so a failure never
    rolls back a sibling job that already succeeded.
    """

    session_factory = get_session_factory()
    processed = 0
    for _ in range(max(batch, 0)):
        async with session_factory() as db:
            # The claim commits before returning, so a crash below leaves a
            # visible ``running`` row instead of a silently lost job.
            job = await claim_next_job(db)
            if job is None:
                break
            job_id = job.id
            try:
                await execute_job(db, job)
            except Exception:
                await db.rollback()
                # Never log the exception payload: it can carry provider secrets.
                logger.warning("image_worker_job_failed job_id=%s", job_id)
        processed += 1
    if processed:
        logger.info("image_worker_processed count=%s", processed)
    return processed


async def run_forever(*, interval: float, batch: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await run_once(batch=batch)
        except Exception:
            # Never log the exception payload: it can carry provider secrets.
            logger.warning("image_worker_cycle_failed")
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
    logger.info("image_worker_started interval=%s batch=%s", args.interval, args.batch)
    await run_forever(interval=args.interval, batch=args.batch, stop=stop)
    logger.info("image_worker_stopped")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Worker durable de generación de imágenes HiTrendy"
    )
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
