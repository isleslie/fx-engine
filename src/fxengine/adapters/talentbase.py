"""talentbase.ng — Tier 1 survey aggregator.

The homepage server-renders one small table per currency ("Dollars to Naira
(USD to NGN)", etc.), each with a Buying Rate and a Selling Rate row. We read
buy/sell for each major and emit them; the engine collapses to a mid.

The page shows only a quote *date* ("Last updated: 12 June 2026 — WAT", and the
same in the <title>) — no time-of-day — so `observed_at` is the fetch time,
matching the other survey adapters. Stamping the date at midnight made this
source read ~17h stale by mid-afternoon and crushed its freshness weight.

robots.txt (checked 2026-06): `User-agent: * / Allow: /` — fully permitted.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

URL = "https://talentbase.ng/"
TARGETS = {"USD", "GBP", "EUR"}

_CODE = re.compile(r"\(([A-Z]{3})\s+to\s+NGN\)", re.IGNORECASE)
_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def _to_float(text: str) -> float | None:
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


def parse(html: str) -> list[tuple[str, float, float]]:
    """Return [(currency, buy, sell), ...] for every currency table found."""
    soup = BeautifulSoup(html, "html.parser")

    out: list[tuple[str, float, float]] = []
    for table in soup.find_all("table"):
        code_match = _CODE.search(table.get_text(" "))
        if code_match is None:
            continue
        buy = sell = None
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            if "buying" in label:
                buy = _to_float(cells[1].get_text())
            elif "selling" in label:
                sell = _to_float(cells[1].get_text())
        if buy is not None and sell is not None:
            out.append((code_match.group(1).upper(), buy, sell))
    return out


class TalentBaseAdapter(BaseAdapter):
    name = "talentbase"
    tier = Tier.AGGREGATOR

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        observed_at = utcnow()
        rows = parse(resp.text)
        out: list[Observation] = []
        for currency, buy, sell in rows:
            if currency not in TARGETS:
                continue
            out.append(Observation(self.name, self.tier, currency, Side.BUY, buy, observed_at))
            out.append(Observation(self.name, self.tier, currency, Side.SELL, sell, observed_at))
        if not out:
            raise RuntimeError("talentbase: no target-currency tables parsed")
        return out
