"""Normalize raw observations into one comparable mid per source per currency.

Rules:
- A source quoting buy+sell collapses to their average.
- A source quoting only one side is taken as-is (street quotes are loose
  enough that a half-spread correction would be false precision; revisit
  with live data).
- Official-tier observations are excluded — the anchor is never an input
  to its own comparison.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from ..models import Observation, Tier


@dataclass(frozen=True, slots=True)
class SourceMid:
    source: str
    tier: Tier
    currency: str
    mid: float
    observed_at: datetime


def to_mids(observations: list[Observation]) -> list[SourceMid]:
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for ob in observations:
        if ob.tier is Tier.OFFICIAL:
            continue
        grouped[(ob.source, ob.currency)].append(ob)

    mids: list[SourceMid] = []
    for (source, currency), obs in grouped.items():
        rate = sum(o.rate for o in obs) / len(obs)
        latest = max(o.observed_at for o in obs)
        mids.append(SourceMid(source, obs[0].tier, currency, rate, latest))
    return mids
