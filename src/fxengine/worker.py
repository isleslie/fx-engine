"""Worker process: scheduled ingestion → consensus → storage.

Run with: python -m fxengine.worker
Runs one ingest immediately at startup (so a fresh deploy has data within
seconds), then on an interval from settings. One adapter failing is logged
and skipped; the run continues with whatever sensors answered.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from apscheduler.schedulers.blocking import BlockingScheduler

from .adapters import live_adapters, make_client, mock_adapters
from .config import settings
from .engine import compute_consensus, to_mids
from .models import Observation, Tier, utcnow
from .storage import Storage

log = logging.getLogger("fxengine.worker")


def get_adapters(client) -> list:
    if settings.use_mock_sources:
        return mock_adapters()
    return live_adapters(client)


async def gather_observations() -> list[Observation]:
    async with make_client() as client:
        adapters = get_adapters(client)
        results = await asyncio.gather(*(a.fetch() for a in adapters), return_exceptions=True)
    observations: list[Observation] = []
    for adapter, result in zip(adapters, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("source %s failed: %s", adapter.name, result)
            continue
        observations.extend(result)
        log.info("source %s: %d observations", adapter.name, len(result))
    return observations


def run_ingest(storage: Storage) -> None:
    observations = asyncio.run(gather_observations())
    if not observations:
        log.error("ingest produced zero observations — nothing stored")
        return
    now = utcnow()

    official = [o for o in observations if o.tier is Tier.OFFICIAL]
    market = [o for o in observations if o.tier is not Tier.OFFICIAL]

    storage.insert_observations(market, ingested_at=now)
    storage.insert_official(official, ingested_at=now)

    by_ccy: dict[str, list] = defaultdict(list)
    for mid in to_mids(market):
        by_ccy[mid.currency].append(mid)

    for currency in settings.currencies:
        consensus, rejected = compute_consensus(by_ccy.get(currency, []))
        if consensus is None:
            log.warning("%s: no market observations this run", currency)
            continue
        storage.insert_consensus(consensus)
        tier_brief = ", ".join(
            f"{tc.tier.value}={tc.rate:.2f}(n{tc.n_sources},w{tc.weight:.2f})"
            for tc in consensus.tiers
        )
        spread = (
            f", survey→P2P {consensus.inter_tier_spread_pct:+.2f}%"
            if consensus.inter_tier_spread_pct is not None
            else ""
        )
        log.info(
            "%s consensus %.2f (confidence %.2f, %d sources, %d rejected: %s) "
            "[%s%s]",
            currency,
            consensus.rate,
            consensus.confidence,
            consensus.n_sources,
            consensus.n_rejected,
            [m.source for m in rejected] or "none",
            tier_brief,
            spread,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    storage = Storage(settings.db_path)
    log.info("db: %s | interval: %dmin | mock=%s",
             settings.db_path, settings.ingest_interval_minutes, settings.use_mock_sources)

    run_ingest(storage)  # immediate first run

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_ingest, "interval", args=[storage],
        minutes=settings.ingest_interval_minutes, id="ingest",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        storage.close()


if __name__ == "__main__":
    main()
