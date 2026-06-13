"""Config-driven Tier-1 survey adapter.

A survey site whose rates are a simple homepage scrape (a repeating element per
currency, with a code and buy/sell or single rate reachable by CSS selector) is
a YAML entry in config/source_registry.yaml — no module needed. This builds one
GenericSurveyAdapter per enabled entry; the worker isolates per-adapter failures,
so one stale selector never costs the others.

Sites needing real custom logic stay bespoke (aboki: multi-page; talentbase:
label-based per-currency tables) — see docs/sources.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
import yaml
from bs4 import BeautifulSoup

from ..config import settings
from ..models import Observation, Side, Tier, utcnow
from .base import BaseAdapter

log = logging.getLogger("fxengine.adapters.generic")

_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def _to_float(text: str | None) -> float | None:
    if not text:
        return None
    m = _NUM.search(text)
    return float(m.group().replace(",", "")) if m else None


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    name: str
    url: str
    container: str
    code_selector: str
    code_pattern: str | None = None
    value_selector: str | None = None
    value_pattern: str | None = None
    buy_selector: str | None = None
    sell_selector: str | None = None
    currencies: tuple[str, ...] | None = None


def load_registry(path=None) -> list[RegistryEntry]:
    """Parse the YAML registry, returning only the enabled entries.

    Returns [] (with a logged warning) if the file is missing or unreadable, so a
    config problem degrades to the bespoke sources rather than aborting ingest.
    """
    p = path or settings.source_registry
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.error("source registry %s unreadable: %s", p, exc)
        return []
    entries: list[RegistryEntry] = []
    for s in raw.get("sources", []):
        if not s.get("enabled", False):
            continue
        ccys = s.get("currencies")
        entries.append(
            RegistryEntry(
                name=s["name"], url=s["url"], container=s["container"],
                code_selector=s["code_selector"], code_pattern=s.get("code_pattern"),
                value_selector=s.get("value_selector"),
                value_pattern=s.get("value_pattern"),
                buy_selector=s.get("buy_selector"), sell_selector=s.get("sell_selector"),
                currencies=tuple(ccys) if ccys else None,
            )
        )
    return entries


def parse_entry(entry: RegistryEntry, html: str, currencies) -> list[tuple[str, Side, float]]:
    """Extract (currency, side, rate) rows for one entry's page."""
    soup = BeautifulSoup(html, "html.parser")
    targets = set(entry.currencies or currencies)
    out: list[tuple[str, Side, float]] = []
    for el in soup.select(entry.container):
        code_el = el.select_one(entry.code_selector)
        if code_el is None:
            continue
        code_text = code_el.get_text(" ", strip=True)
        if entry.code_pattern:
            m = re.search(entry.code_pattern, code_text)
            if m is None:
                continue
            code = m.group(1).upper()
        else:
            code = code_text.strip().upper()
        if code not in targets:
            continue

        if entry.value_selector and entry.value_pattern:
            ve = el.select_one(entry.value_selector)
            if ve is None:
                continue
            m = re.search(entry.value_pattern, ve.get_text(" ", strip=True))
            if m is None:
                continue
            groups = m.groups()
            if len(groups) >= 2:
                buy, sell = _to_float(groups[0]), _to_float(groups[1])
                if buy and sell:
                    out += [(code, Side.BUY, buy), (code, Side.SELL, sell)]
            elif groups:
                mid = _to_float(groups[0])
                if mid:
                    out.append((code, Side.MID, mid))
        elif entry.buy_selector and entry.sell_selector:
            buy = _to_float((el.select_one(entry.buy_selector) or _Empty()).get_text())
            sell = _to_float((el.select_one(entry.sell_selector) or _Empty()).get_text())
            if buy and sell:
                out += [(code, Side.BUY, buy), (code, Side.SELL, sell)]
    return out


class _Empty:
    def get_text(self, *a, **k) -> str:
        return ""


class GenericSurveyAdapter(BaseAdapter):
    tier = Tier.AGGREGATOR

    def __init__(self, client: httpx.AsyncClient, entry: RegistryEntry) -> None:
        super().__init__(client)
        self.entry = entry
        self.name = entry.name

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(self.entry.url)
        resp.raise_for_status()
        now = utcnow()
        rows = parse_entry(self.entry, resp.text, settings.currencies)
        out = [Observation(self.name, self.tier, c, side, rate, now) for c, side, rate in rows]
        if not out:
            raise RuntimeError(f"{self.name}: no target-currency rows parsed")
        return out


def registry_adapters(client: httpx.AsyncClient) -> list[GenericSurveyAdapter]:
    """One adapter per enabled registry entry."""
    return [GenericSurveyAdapter(client, e) for e in load_registry()]
