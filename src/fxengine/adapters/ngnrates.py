"""ngnrates.com — Tier 1 survey aggregator.

The homepage server-renders a card per currency. Each card carries the ISO
code (`span.ng-fc`) and several market rows; we want the Black Market row,
linked as `<a href="…/black-market">` and holding `span.ng-val` = "buy / sell"
(e.g. "1,390 / 1,400"). We emit BUY and SELL observations per major and let
the engine collapse them to a mid.

No per-rate timestamp is shown, so `observed_at` is the fetch time.

robots.txt (checked 2026-06): `User-agent: * / Allow: /` — fully permitted.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

URL = "https://www.ngnrates.com/"
TARGETS = {"USD", "GBP", "EUR"}

_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def _to_float(text: str) -> float | None:
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


def parse(html: str) -> list[tuple[str, float, float]]:
    """Return (currency, buy, sell) for every currency card with a black-market row."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, float, float]] = []
    for box in soup.select("div.ng-box"):
        code_el = box.select_one("span.ng-fc")
        link = box.select_one('a[href*="/black-market"]')
        if code_el is None or link is None:
            continue
        val_el = link.select_one("span.ng-val")
        if val_el is None:
            continue
        parts = val_el.get_text().split("/")
        if len(parts) != 2:
            continue
        buy, sell = _to_float(parts[0]), _to_float(parts[1])
        if buy is None or sell is None:
            continue
        out.append((code_el.get_text(strip=True).upper(), buy, sell))
    return out


class NgnRatesAdapter(BaseAdapter):
    name = "ngnrates"
    tier = Tier.AGGREGATOR

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        now = utcnow()
        out: list[Observation] = []
        for currency, buy, sell in parse(resp.text):
            if currency not in TARGETS:
                continue
            out.append(Observation(self.name, self.tier, currency, Side.BUY, buy, now))
            out.append(Observation(self.name, self.tier, currency, Side.SELL, sell, now))
        if not out:
            raise RuntimeError("ngnrates: no target-currency black-market rows parsed")
        return out
