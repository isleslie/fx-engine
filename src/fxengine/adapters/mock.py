"""Mock sources.

These stand in for the live tiers so the entire pipeline — ingest →
consensus → storage → API → dashboard — runs end-to-end before any real
scraper exists. They generate plausible, slightly-divergent rates around a
slowly drifting "true" parallel rate, with one deliberately noisy source so
the outlier-rejection path is exercised on every run.

Replace via `settings.use_mock_sources = False` once live adapters land.
"""

from __future__ import annotations

import math
import random
import time

from ..models import Observation, Side, Tier, utcnow

# Rough mid levels per currency (NGN per unit) used as the mock anchor.
_BASE = {"USD": 1480.0, "GBP": 1980.0, "EUR": 1710.0}
_OFFICIAL_DISCOUNT = 0.045  # official trades ~4.5% below parallel in the mock


def _drift(currency: str) -> float:
    """Deterministic slow sine drift so charts show movement across runs."""
    t = time.time() / 3600.0  # hours
    return _BASE[currency] * (1 + 0.01 * math.sin(t / 6 + hash(currency) % 7))


class MockSurveyAdapter:
    """Tier 1 stand-in: a survey site quoting buy/sell around the mid."""

    tier = Tier.AGGREGATOR

    def __init__(self, name: str, bias: float = 0.0, noise: float = 0.002) -> None:
        self.name = name
        self.bias = bias
        self.noise = noise

    async def fetch(self) -> list[Observation]:
        now = utcnow()
        out: list[Observation] = []
        for ccy, _ in _BASE.items():
            mid = _drift(ccy) * (1 + self.bias + random.gauss(0, self.noise))
            half_spread = mid * 0.004
            out.append(
                Observation(self.name, self.tier, ccy, Side.BUY, mid - half_spread, now)
            )
            out.append(
                Observation(self.name, self.tier, ccy, Side.SELL, mid + half_spread, now)
            )
        return out


class MockP2PAdapter:
    """Tier 2 stand-in: USDT/NGN order-book mid (USD only)."""

    tier = Tier.P2P

    def __init__(self, name: str = "mock_p2p") -> None:
        self.name = name

    async def fetch(self) -> list[Observation]:
        mid = _drift("USD") * (1 + random.gauss(0, 0.0015))
        return [Observation(self.name, self.tier, "USD", Side.MID, mid, utcnow())]


class MockOfficialAdapter:
    """Official anchor stand-in (CBN). Never a consensus input."""

    tier = Tier.OFFICIAL
    name = "mock_cbn"

    async def fetch(self) -> list[Observation]:
        now = utcnow()
        return [
            Observation(
                self.name, self.tier, ccy, Side.MID, _drift(ccy) * (1 - _OFFICIAL_DISCOUNT), now
            )
            for ccy in _BASE
        ]


def mock_adapters() -> list:
    """Five survey sensors (one wild), one P2P feed, one official anchor."""
    return [
        MockSurveyAdapter("mock_aboki"),
        MockSurveyAdapter("mock_nairatoday", bias=0.001),
        MockSurveyAdapter("mock_nairaspot", bias=-0.001),
        MockSurveyAdapter("mock_ngnrates", bias=0.002),
        MockSurveyAdapter("mock_outlier", bias=0.08, noise=0.01),  # exercises rejection
        MockP2PAdapter(),
        MockOfficialAdapter(),
    ]
