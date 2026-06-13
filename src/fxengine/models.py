"""Core domain models shared by adapters, engine, storage and API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"
    MID = "mid"


class Tier(StrEnum):
    """Source tiers from docs/sources.md."""

    AGGREGATOR = "tier1_aggregator"  # survey-based sites (aboki, nairatoday, etc.)
    P2P = "tier2_p2p"  # transaction-based crypto signal (USDT/NGN)
    FINTECH = "tier3_fintech"  # digital BDC / fintech published rates
    OFFICIAL = "official"  # CBN anchor — never a consensus input


@dataclass(frozen=True, slots=True)
class Observation:
    """A single rate reading from a single source.

    This is the adapter contract: every adapter, live or mock, returns a
    list of these and nothing else.
    """

    source: str
    tier: Tier
    currency: str  # ISO pair vs NGN, e.g. "USD"
    side: Side
    rate: float  # NGN per 1 unit of `currency`
    observed_at: datetime  # when the source says the rate is from (UTC)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError(f"rate must be positive, got {self.rate}")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware (UTC)")


@dataclass(frozen=True, slots=True)
class TierConsensus:
    """Per-tier sub-consensus: one source mechanism's own view of a currency.

    Tiers (survey aggregators vs transaction-based P2P/exchange) measure related
    but distinct things, so each gets its own outlier rejection and weighted
    mid before the tiers are blended. `weight` is the normalised blend weight
    actually applied to this tier in the final consensus this run.
    """

    tier: Tier
    rate: float
    n_sources: int
    n_rejected: int
    dispersion: float
    weight: float


@dataclass(frozen=True, slots=True)
class ConsensusRate:
    """The engine's output for one currency at one point in time.

    `rate` is the tier-blended consensus; `tiers` carries each mechanism's
    sub-consensus and `inter_tier_spread_pct` the signed survey→P2P gap (None
    unless both mechanisms are present). The trailing fields default so older
    positional construction and stored rows without them remain valid.
    """

    currency: str
    rate: float  # tier-blended consensus, NGN per unit
    confidence: float  # 0..1, higher = tight, deep, and cross-mechanism agreement
    n_sources: int  # sources surviving outlier rejection (across tiers)
    n_rejected: int  # sources dropped as outliers/stale (across tiers)
    dispersion: float  # blend-weighted within-tier relative MAD (0 = perfect agreement)
    computed_at: datetime
    inter_tier_spread_pct: float | None = None  # signed (P2P - survey) / survey, %
    tiers: tuple[TierConsensus, ...] = ()  # per-tier sub-consensus, in-memory carrier


def utcnow() -> datetime:
    return datetime.now(UTC)
