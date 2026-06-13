"""abokiforex.app — Tier 1 survey aggregator.

Aboki publishes one headline black-market rate per currency on a dedicated
page each (no separate buy/sell), refreshed hourly. Each page carries a
forward converter table whose first data row is "1 <unit> to Naira = <rate>";
that cell is the rate. The page shows only a quote *date* in the <h1>
(M/D/YYYY) — no time-of-day — so `observed_at` is the fetch time, matching the
other survey adapters; this keeps freshness weighting comparable across sources
rather than treating a date-only page as 17h stale by mid-afternoon.

We fetch USD/GBP/EUR (one page each) and emit a single MID observation per
currency. A page that fails or fails to parse is skipped; the adapter only
raises if every page is unusable, so a broken EUR page never costs us USD.

robots.txt (checked 2026-06): `User-agent: * / Disallow:` — nothing blocked.
Page states the data is information-only; read-only scrape, polite UA.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

BASE = "https://abokiforex.app"
# currency -> page path
PAGES = {
    "USD": "/dollar-to-naira-black-market",
    "GBP": "/pounds-to-naira-black-market",
    "EUR": "/euro-to-naira-black-market",
}

_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def _to_float(text: str) -> float | None:
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


def parse(html: str) -> float:
    """Extract the headline rate from one aboki currency page."""
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    if table is None:
        raise ValueError("aboki: no rate table found")
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            value = _to_float(cells[1].get_text())
            # The forward table's first data row ("1 X to Naira") is a full-naira
            # figure; the reverse table yields fractions — take the first > 1.
            if value is not None and value > 1:
                return value
    raise ValueError("aboki: could not read a rate from the table")


class AbokiAdapter(BaseAdapter):
    name = "aboki"
    tier = Tier.AGGREGATOR

    async def fetch(self) -> list[Observation]:
        observed_at = utcnow()
        out: list[Observation] = []
        errors: list[str] = []
        for currency, path in PAGES.items():
            try:
                resp = await self.client.get(BASE + path)
                resp.raise_for_status()
                rate = parse(resp.text)
            except Exception as exc:  # noqa: BLE001 — collect, decide after loop
                errors.append(f"{currency}: {exc}")
                continue
            out.append(
                Observation(self.name, self.tier, currency, Side.MID, rate, observed_at)
            )
        if not out:
            raise RuntimeError(f"aboki: all pages failed ({'; '.join(errors)})")
        return out
