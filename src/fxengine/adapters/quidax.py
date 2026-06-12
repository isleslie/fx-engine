"""Quidax — Tier 2 P2P/exchange signal (USDT/NGN ≈ USD/NGN).

Quidax is a SEC-licensed Nigerian exchange with a direct NGN order book. Its
public market-data API exposes a ticker per market; for `usdtngn` we take the
order-book mid — the average of best buy (bid) and best sell (ask) — as a
single transaction-based USD signal. This is the strongest non-survey sensor:
prices where trades actually clear, not a quoted survey.

Endpoint: GET /api/v1/markets/tickers/usdtngn →
  {"data": {"at": <unix>, "ticker": {"buy": "...", "sell": "...", ...}}}

robots.txt (checked 2026-06): only `Disallow: /*?*attrc=`; the documented
public market-data API is permitted. Read-only market data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import Observation, Side, Tier
from .base import BaseAdapter

URL = "https://app.quidax.io/api/v1/markets/tickers/usdtngn"


def parse(payload: dict) -> Observation:
    """Order-book mid USDT/NGN as a single USD MID observation."""
    data = payload["data"]
    ticker = data["ticker"]
    buy, sell = float(ticker["buy"]), float(ticker["sell"])
    mid = (buy + sell) / 2
    observed_at = datetime.fromtimestamp(int(data["at"]), tz=UTC)
    return Observation("quidax", Tier.P2P, "USD", Side.MID, mid, observed_at)


class QuidaxAdapter(BaseAdapter):
    name = "quidax"
    tier = Tier.P2P

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        return [parse(resp.json())]
