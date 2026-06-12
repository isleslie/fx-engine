"""Consensus: a confidence-weighted central rate per currency.

Weighting, per surviving source:
- freshness: exponential decay with a configurable half-life, so an
  hours-stale survey contributes less than a minutes-old order book.
- agreement: 1 / (1 + z) where z is the source's scaled-MAD distance from
  the median — sources that sit with the pack count more than stragglers
  that survived the cut.

Confidence (0..1) combines:
- tightness: how small the relative dispersion of survivors is.
- coverage: how many independent sources survived (saturating at 6).

This is the methodology the README sells; keep changes here documented in
docs/architecture.md.
"""

from __future__ import annotations

import math

import numpy as np

from ..config import settings
from ..models import ConsensusRate, utcnow
from .normalize import SourceMid
from .outliers import MAD_SCALE, reject_outliers

_FULL_PANEL = 6  # sources at/above this count as full coverage
_TIGHT_DISPERSION = 0.02  # 2% rel-MAD ~ zero tightness credit beyond here


def compute_consensus(
    mids: list[SourceMid],
    k: float | None = None,
) -> tuple[ConsensusRate | None, list[SourceMid]]:
    """Compute consensus for one currency. Returns (consensus, rejected).

    Returns (None, []) when there are no observations at all.
    """
    if not mids:
        return None, []
    currency = mids[0].currency
    if any(m.currency != currency for m in mids):
        raise ValueError("compute_consensus expects a single currency per call")

    kept, rejected = reject_outliers(mids, k=k if k is not None else settings.mad_k)

    now = utcnow()
    rates = np.array([m.mid for m in kept], dtype=float)
    med = float(np.median(rates))
    mad = float(np.median(np.abs(rates - med))) * MAD_SCALE

    half_life = settings.freshness_half_life_minutes
    weights = []
    for m, r in zip(kept, rates, strict=True):
        age_min = max((now - m.observed_at).total_seconds() / 60.0, 0.0)
        freshness = 0.5 ** (age_min / half_life)
        z = abs(r - med) / mad if mad > 0 else 0.0
        agreement = 1.0 / (1.0 + z)
        weights.append(freshness * agreement)
    w = np.array(weights, dtype=float)
    if w.sum() == 0:  # everything ancient; fall back to unweighted
        w = np.ones_like(w)

    rate = float(np.average(rates, weights=w))
    dispersion = mad / med if med else 0.0

    tightness = max(0.0, 1.0 - dispersion / _TIGHT_DISPERSION)
    coverage = min(len(kept) / _FULL_PANEL, 1.0)
    confidence = round(math.sqrt(tightness * coverage), 4)

    return (
        ConsensusRate(
            currency=currency,
            rate=round(rate, 2),
            confidence=confidence,
            n_sources=len(kept),
            n_rejected=len(rejected),
            dispersion=round(dispersion, 6),
            computed_at=now,
        ),
        rejected,
    )
