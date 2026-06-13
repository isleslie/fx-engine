"""API response models. These shapes are mirrored 1:1 by the TypeScript
types in frontend/src/lib/api.ts — change them together."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TierOut(BaseModel):
    tier: str
    rate: float
    n_sources: int
    n_rejected: int
    dispersion: float
    weight: float  # normalised blend weight applied this run


class ConsensusOut(BaseModel):
    currency: str
    rate: float
    confidence: float
    n_sources: int
    n_rejected: int
    dispersion: float
    computed_at: datetime
    inter_tier_spread_pct: float | None = None  # signed (P2P - survey) / survey, %
    tiers: list[TierOut] = []  # per-mechanism sub-consensus


class OfficialOut(BaseModel):
    source: str
    currency: str
    rate: float
    observed_at: datetime


class LatestOut(BaseModel):
    consensus: ConsensusOut | None
    official: OfficialOut | None
    spread_abs: float | None  # consensus - official, NGN
    spread_pct: float | None  # spread as % of official


class HistoryPoint(BaseModel):
    t: datetime
    consensus: float | None = None
    official: float | None = None


class HistoryOut(BaseModel):
    currency: str
    days: int
    points: list[HistoryPoint]


class SourceOut(BaseModel):
    source: str
    tier: str
    mid: float
    observed_at: datetime
    divergence_pct: float | None  # vs latest consensus
    rejected: bool = False  # cut as an outlier within its tier this run
    reliability: float | None = None  # slow EWMA trust score (0..1), None if unseen
    correlated_with: str | None = None  # a survey peer this source mirrors, if flagged


class SourcesOut(BaseModel):
    currency: str
    consensus: float | None
    sources: list[SourceOut]


class HealthOut(BaseModel):
    status: str
    db: bool
    last_consensus_at: datetime | None
