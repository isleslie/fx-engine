"""talentbase.ng — Tier 1 survey aggregator.

The homepage server-renders one small table per currency ("Dollars to Naira
(USD to NGN)", etc.), each with a Buying Rate and a Selling Rate row. The
quote date sits in the page <title> ("… Exchange Rate 12 June 2026"). We read
buy/sell for each major and emit them; the engine collapses to a mid.

robots.txt (checked 2026-06): `User-agent: * / Allow: /` — fully permitted.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

URL = "https://talentbase.ng/"
TARGETS = {"USD", "GBP", "EUR"}

_CODE = re.compile(r"\(([A-Z]{3})\s+to\s+NGN\)", re.IGNORECASE)
_NUM = re.compile(r"[\d,]+(?:\.\d+)?")
_DATE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")


def _to_float(text: str) -> float | None:
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


def _observed_at(soup: BeautifulSoup) -> datetime:
    title = soup.find("title")
    if title and (m := _DATE.search(title.get_text())):
        try:
            return datetime.strptime(m.group(0), "%d %B %Y").replace(tzinfo=UTC)
        except ValueError:
            pass
    return utcnow()


def parse(html: str) -> tuple[datetime, list[tuple[str, float, float]]]:
    """Return (observed_at, [(currency, buy, sell), ...])."""
    soup = BeautifulSoup(html, "html.parser")
    observed_at = _observed_at(soup)

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
    return observed_at, out


class TalentBaseAdapter(BaseAdapter):
    name = "talentbase"
    tier = Tier.AGGREGATOR

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        observed_at, rows = parse(resp.text)
        out: list[Observation] = []
        for currency, buy, sell in rows:
            if currency not in TARGETS:
                continue
            out.append(Observation(self.name, self.tier, currency, Side.BUY, buy, observed_at))
            out.append(Observation(self.name, self.tier, currency, Side.SELL, sell, observed_at))
        if not out:
            raise RuntimeError("talentbase: no target-currency tables parsed")
        return out
