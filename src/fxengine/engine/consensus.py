"""Tier-aware consensus: reconcile distinct rate-discovery mechanisms.

Survey aggregators (street/BDC cash quotes) and transaction-based feeds (USDT/NGN
order books and P2P) are measuring related but *different* things — a persistent
gap between them is plausibly structural, not error. So we do NOT pool them and
median-MAD the lot; instead each tier is reconciled on its own and the tiers are
then blended:

1. Group surviving observations by tier within a currency.
2. Outlier rejection runs WITHIN each tier only (outliers.py). A tight survey
   pack can never evict the transaction-based tier, or vice versa — which is the
   bug the single-pool design had (the lone P2P price looked like the anomaly
   against four near-identical surveys and got cut every run).
3. Each tier gets a sub-consensus: the existing freshness × agreement weighting,
   applied within the tier.
4. The tier sub-consensuses are blended with configurable weights
   (settings.tier_weights), renormalised over the tiers actually present — so a
   currency with no P2P tier (GBP/EUR today) falls back to survey-only cleanly.

Confidence (0..1) now rewards *two independent mechanisms agreeing*, each with
*several sources*, and caps single-mechanism or single-source reliance:

    within_quality   = Σ_t weight_t · sqrt(tightness_t × depth_t)
    mechanism_factor = cross-tier agreement      (if ≥2 tiers present)
                     = SINGLE_TIER_CAP           (if only one tier present)
    confidence       = within_quality × mechanism_factor

where per tier: tightness fades to 0 as relative dispersion reaches 2%, depth
saturates at FULL_TIER surviving sources; cross-tier agreement fades to 0 as the
relative spread between tier rates reaches CROSS_TIER_TOL. So a single tight
mechanism can no longer score near-perfect (it is capped), while two mechanisms
that genuinely agree can.

The blended rate, each tier sub-consensus, and the signed survey→P2P spread are
all reported — that spread is itself a signal (is the gap structural or noise?).

Keep changes here documented in docs/architecture.md.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..config import settings
from ..models import ConsensusRate, Tier, TierConsensus, utcnow
from .normalize import SourceMid
from .outliers import MAD_SCALE, reject_outliers
from .reliability import weight_factor

_FULL_TIER = 3  # surviving sources within a tier counting as full depth
_TIGHT_DISPERSION = 0.02  # 2% within-tier rel-MAD ~ zero tightness credit beyond here
_CROSS_TIER_TOL = 0.03  # 3% spread between tier rates ~ zero cross-tier agreement
_SINGLE_TIER_CAP = 0.7  # one mechanism, however tight, cannot exceed this confidence


def _sub_consensus(
    mids: list[SourceMid], k: float,
    reliability: dict[str, float], penalty: dict[str, float],
):
    """Reconcile one tier. Returns (rate, dispersion, quality, kept, rejected)."""
    kept, rejected = reject_outliers(mids, k=k)
    now = utcnow()
    rates = np.array([m.mid for m in kept], dtype=float)
    med = float(np.median(rates))
    mad = float(np.median(np.abs(rates - med))) * MAD_SCALE

    half_life = settings.freshness_half_life_minutes
    prior = settings.reliability_prior
    weights = []
    for m, r in zip(kept, rates, strict=True):
        age_min = max((now - m.observed_at).total_seconds() / 60.0, 0.0)
        freshness = 0.5 ** (age_min / half_life)
        z = abs(r - med) / mad if mad > 0 else 0.0
        trust = weight_factor(reliability.get(m.source, prior))
        weights.append(freshness * (1.0 / (1.0 + z)) * trust * penalty.get(m.source, 1.0))
    w = np.array(weights, dtype=float)
    if w.sum() == 0:  # everything ancient; fall back to unweighted
        w = np.ones_like(w)

    rate = float(np.average(rates, weights=w))
    dispersion = mad / med if med else 0.0
    tightness = max(0.0, 1.0 - dispersion / _TIGHT_DISPERSION)
    depth = min(len(kept) / _FULL_TIER, 1.0)
    quality = math.sqrt(tightness * depth)
    return rate, dispersion, quality, kept, rejected


def compute_consensus(
    mids: list[SourceMid],
    k: float | None = None,
    reliability: dict[str, float] | None = None,
    weight_penalty: dict[str, float] | None = None,
) -> tuple[ConsensusRate | None, list[SourceMid]]:
    """Tier-aware consensus for one currency. Returns (consensus, rejected).

    Returns (None, []) when there are no observations at all. `rejected` is the
    union of every tier's rejected sources. `reliability` maps source -> score
    (0..1); absent sources use the neutral prior, so passing None leaves all
    weights uniform and the rate unchanged. `weight_penalty` maps source -> a
    within-tier weight multiplier (the independence guard halves copycats);
    absent sources default to 1.0.
    """
    if not mids:
        return None, []
    currency = mids[0].currency
    if any(m.currency != currency for m in mids):
        raise ValueError("compute_consensus expects a single currency per call")
    k = k if k is not None else settings.mad_k
    rel = reliability or {}
    penalty = weight_penalty or {}
    now = utcnow()

    by_tier: dict[Tier, list[SourceMid]] = defaultdict(list)
    for m in mids:
        by_tier[m.tier].append(m)

    # Reconcile each tier on its own.
    results = {tier: _sub_consensus(tmids, k, rel, penalty) for tier, tmids in by_tier.items()}

    # Blend weights: configured per tier, renormalised over the tiers present.
    raw = {t: settings.tier_weights.get(t.value, 0.0) for t in results}
    total = sum(raw.values())
    if total <= 0:  # present but unweighted → equal weight fallback
        raw = {t: 1.0 for t in results}
        total = float(len(results))
    norm = {t: raw[t] / total for t in results}

    blended_rate = sum(norm[t] * results[t][0] for t in results)

    tiers_out: list[TierConsensus] = []
    rejected_all: list[SourceMid] = []
    n_sources = n_rejected = 0
    dispersion_blend = within_quality = 0.0
    for t, (rate, dispersion, quality, kept, rejected) in results.items():
        tiers_out.append(
            TierConsensus(
                tier=t, rate=round(rate, 2), n_sources=len(kept),
                n_rejected=len(rejected), dispersion=round(dispersion, 6),
                weight=round(norm[t], 4),
            )
        )
        rejected_all.extend(rejected)
        n_sources += len(kept)
        n_rejected += len(rejected)
        dispersion_blend += norm[t] * dispersion
        within_quality += norm[t] * quality

    # Cross-mechanism factor + the structural survey↔P2P spread.
    inter_tier_spread_pct = None
    if len(results) >= 2:
        tier_rates = [results[t][0] for t in results]
        med_rate = float(np.median(tier_rates))
        rel_spread = (max(tier_rates) - min(tier_rates)) / med_rate if med_rate else 0.0
        mechanism_factor = max(0.0, 1.0 - rel_spread / _CROSS_TIER_TOL)
        if Tier.AGGREGATOR in results and Tier.P2P in results:
            survey, p2p = results[Tier.AGGREGATOR][0], results[Tier.P2P][0]
            inter_tier_spread_pct = round((p2p - survey) / survey * 100, 3) if survey else None
    else:
        mechanism_factor = _SINGLE_TIER_CAP

    confidence = round(within_quality * mechanism_factor, 4)

    return (
        ConsensusRate(
            currency=currency,
            rate=round(blended_rate, 2),
            confidence=confidence,
            n_sources=n_sources,
            n_rejected=n_rejected,
            dispersion=round(dispersion_blend, 6),
            computed_at=now,
            inter_tier_spread_pct=inter_tier_spread_pct,
            tiers=tuple(sorted(tiers_out, key=lambda tc: tc.tier.value)),
            rejected_sources=tuple(sorted(m.source for m in rejected_all)),
        ),
        rejected_all,
    )
