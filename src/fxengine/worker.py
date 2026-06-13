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
from dataclasses import replace

from apscheduler.schedulers.blocking import BlockingScheduler

from .adapters import live_adapters, make_client, mock_adapters
from .config import settings
from .engine import compute_consensus, to_mids, update_reliability
from .engine.independence import flag_correlated_pairs
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


def _correlation_guard(storage, currency, reliability):
    """Flag copycat survey pairs over recent history; halve the weaker member.

    Returns (pairs, penalty) where penalty maps the lower-reliability member of
    each flagged pair to settings.correlation_penalty.
    """
    history = storage.recent_source_mids(
        currency, Tier.AGGREGATOR.value, settings.correlation_runs
    )
    pairs = flag_correlated_pairs(
        history,
        tol=settings.correlation_tol,
        threshold=settings.correlation_threshold,
        min_runs=settings.correlation_min_runs,
    )
    prior = settings.reliability_prior
    penalty: dict[str, float] = {}
    for a, b in pairs:
        weaker = a if reliability.get(a, prior) <= reliability.get(b, prior) else b
        penalty[weaker] = settings.correlation_penalty
    return pairs, penalty


def _update_reliability(storage, currency, mids, consensus, rejected, prev_scores) -> None:
    """EWMA-update each participating source against its OWN tier sub-consensus.

    A source cut within its tier takes the maximum error (E_MAX); a kept source
    is scored on its distance from its tier rate. Compared per tier so the
    structural survey↔P2P gap never penalises a source for its mechanism.
    """
    tier_rate = {t.tier: t.rate for t in consensus.tiers}
    rejected_names = {m.source for m in rejected}
    e_max = settings.reliability_error_max
    prior = settings.reliability_prior
    for m in mids:
        if m.source in rejected_names:
            error = e_max
        else:
            tr = tier_rate.get(m.tier)
            error = abs(m.mid - tr) / tr if tr else e_max
        new_score = update_reliability(prev_scores.get(m.source, prior), error)
        storage.upsert_reliability(currency, m.source, new_score, consensus.computed_at)


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
        mids = by_ccy.get(currency, [])
        reliability = storage.reliability_scores(currency)
        pairs, penalty = _correlation_guard(storage, currency, reliability)
        consensus, rejected = compute_consensus(
            mids, reliability=reliability, weight_penalty=penalty
        )
        if consensus is None:
            log.warning("%s: no market observations this run", currency)
            continue
        consensus = replace(consensus, correlated_pairs=tuple(pairs))
        storage.insert_consensus(consensus)
        _update_reliability(storage, currency, mids, consensus, rejected, reliability)
        if pairs:
            log.info("%s correlated survey pairs %s; downweighted %s",
                     currency, pairs, sorted(penalty))
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
