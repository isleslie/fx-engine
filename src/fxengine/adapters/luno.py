"""Luno — Tier 2 exchange signal (USDT/NGN ≈ USD/NGN).

Luno runs a direct NGN order book and exposes the standard documented public
market-data ticker (no auth) at `/api/1/ticker`. For the `USDTNGN` pair we take
the order-book mid — the average of best bid and best ask — as a single
transaction-based USD signal, the same shape as the Quidax adapter. A second
independent order-book source means the P2P tier is no longer a single quote.

Endpoint: GET /api/1/ticker?pair=USDTNGN →
  {"pair":"USDTNGN","timestamp":<unix_ms>,"bid":"..","ask":"..",
   "last_trade":"..","rolling_24_hour_volume":"..","status":"ACTIVE"}

robots.txt (checked 2026-06): www.luno.com `User-agent: * / Allow: /`; the
api.luno.com market-data API is the documented public endpoint. Read-only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import Observation, Side, Tier
from .base import BaseAdapter

URL = "https://api.luno.com/api/1/ticker?pair=USDTNGN"


def parse(payload: dict) -> Observation:
    """Order-book mid USDT/NGN as a single USD MID observation."""
    if payload.get("status") != "ACTIVE":
        raise ValueError(f"luno: market not active (status={payload.get('status')!r})")
    bid, ask = float(payload["bid"]), float(payload["ask"])
    if bid <= 0 or ask <= 0:
        raise ValueError(f"luno: non-positive bid/ask ({bid}/{ask})")
    mid = (bid + ask) / 2
    # Luno timestamps are unix milliseconds.
    observed_at = datetime.fromtimestamp(int(payload["timestamp"]) / 1000, tz=UTC)
    return Observation("luno", Tier.P2P, "USD", Side.MID, mid, observed_at)


class LunoAdapter(BaseAdapter):
    name = "luno"
    tier = Tier.P2P

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        return [parse(resp.json())]
