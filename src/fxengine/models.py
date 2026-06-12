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

    AGGREGATOR = "tier1_aggregator"  # survey-based sites (aboki, nairatoday, ...)
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
class ConsensusRate:
    """The engine's output for one currency at one point in time."""

    currency: str
    rate: float  # confidence-weighted consensus, NGN per unit
    confidence: float  # 0..1, higher = sources tightly clustered & fresh
    n_sources: int  # sources surviving outlier rejection
    n_rejected: int  # sources dropped as outliers/stale
    dispersion: float  # relative MAD of surviving mids (0 = perfect agreement)
    computed_at: datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
