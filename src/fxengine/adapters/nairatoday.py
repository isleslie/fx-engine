"""nairatoday.com — Tier 1 survey aggregator.

The homepage server-renders a clean rate table (`table.nt-rates-table`) with
columns Currency / Buy / Sell / CBN / Change. The currency cell carries the
ISO code in parens, e.g. "🇺🇸US Dollar (USD)". We read Buy and Sell for each
major and emit them as observations; the engine collapses them to a mid. The
CBN column here is informational only — the official anchor comes from the
dedicated CBN adapter, never a Tier-1 page.

No per-row timestamp is shown, so `observed_at` is the fetch time.

robots.txt (checked 2026-06): `Allow: /`, `Disallow: /api/` + crawl-delay 1.
We scrape the rendered homepage only — never the disallowed API.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

URL = "https://nairatoday.com/"
TARGETS = {"USD", "GBP", "EUR"}

_CODE = re.compile(r"\(([A-Z]{3})\)")
_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def _to_float(text: str) -> float | None:
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


def parse(html: str) -> list[tuple[str, float, float]]:
    """Return (currency, buy, sell) per row of the nairatoday rate table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.nt-rates-table")
    if table is None:
        raise ValueError("nairatoday: rate table not found")

    out: list[tuple[str, float, float]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue  # header row (uses <th>) or malformed
        code_match = _CODE.search(cells[0].get_text())
        if code_match is None:
            continue
        buy, sell = _to_float(cells[1].get_text()), _to_float(cells[2].get_text())
        if buy is None or sell is None:
            continue
        out.append((code_match.group(1), buy, sell))
    return out


class NairaTodayAdapter(BaseAdapter):
    name = "nairatoday"
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
            raise RuntimeError("nairatoday: no target-currency rows parsed")
        return out
