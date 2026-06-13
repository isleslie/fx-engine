"""Config-driven Tier-1 registry tests. Offline: respx + saved fixtures.

The parametrized test loops every ENABLED registry entry against
tests/fixtures/<name>.html, so adding a registry source automatically requires
a fixture and gets a smoke test for free.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.generic import (
    GenericSurveyAdapter,
    load_registry,
    parse_entry,
)
from fxengine.models import Side, Tier

FIX = Path(__file__).parent / "fixtures"
MAJORS = ["USD", "GBP", "EUR"]
ENABLED = load_registry()


def _by_name(name: str):
    return next(e for e in ENABLED if e.name == name)


def _rows(name: str) -> dict[tuple[str, Side], float]:
    entry = _by_name(name)
    html = (FIX / f"{name}.html").read_text(encoding="utf-8")
    return {(c, side): rate for c, side, rate in parse_entry(entry, html, MAJORS)}


@pytest.mark.parametrize("entry", ENABLED, ids=lambda e: e.name)
def test_enabled_entry_extracts_all_majors(entry):
    # Requires tests/fixtures/<name>.html — a new registry source needs a fixture.
    html = (FIX / f"{entry.name}.html").read_text(encoding="utf-8")
    codes = {c for c, _, _ in parse_entry(entry, html, MAJORS)}
    assert set(MAJORS) <= codes


def test_ngnrates_values_match_legacy_parser():
    r = _rows("ngnrates")
    assert (r[("USD", Side.BUY)], r[("USD", Side.SELL)]) == (1390.0, 1400.0)
    assert (r[("EUR", Side.BUY)], r[("EUR", Side.SELL)]) == (1595.0, 1640.0)
    assert (r[("GBP", Side.BUY)], r[("GBP", Side.SELL)]) == (1850.0, 1880.0)


def test_nairatoday_values_match_legacy_parser():
    r = _rows("nairatoday")
    assert (r[("USD", Side.BUY)], r[("USD", Side.SELL)]) == (1388.0, 1400.0)
    assert (r[("GBP", Side.BUY)], r[("GBP", Side.SELL)]) == (1840.0, 1880.0)
    assert (r[("EUR", Side.BUY)], r[("EUR", Side.SELL)]) == (1590.0, 1620.0)


def test_disabled_entries_excluded():
    names = {e.name for e in ENABLED}
    assert "fxratetoday" not in names  # enabled: false in the registry
    assert {"ngnrates", "nairatoday"} <= names


def test_missing_registry_degrades_to_empty(tmp_path):
    assert load_registry(tmp_path / "nope.yaml") == []


@respx.mock
def test_generic_adapter_fetch_emits_filtered_majors():
    entry = _by_name("ngnrates")
    html = (FIX / "ngnrates.html").read_text(encoding="utf-8")
    respx.get(entry.url).mock(return_value=httpx.Response(200, text=html))

    async def run():
        async with make_client() as client:
            return await GenericSurveyAdapter(client, entry).fetch()

    obs = asyncio.run(run())
    assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}  # minors filtered out
    usd = {o.side: o.rate for o in obs if o.currency == "USD"}
    assert usd[Side.BUY] == 1390.0 and usd[Side.SELL] == 1400.0
    assert all(o.tier is Tier.AGGREGATOR and o.source == "ngnrates" for o in obs)
