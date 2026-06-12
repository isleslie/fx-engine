"""abokiforex.app adapter tests. Offline: respx serves saved HTML fixtures."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.aboki import BASE, PAGES, AbokiAdapter, parse
from fxengine.adapters.base import make_client
from fxengine.models import Side, Tier

FIX = Path(__file__).parent / "fixtures"
USD = (FIX / "aboki_usd.html").read_text(encoding="utf-8")
GBP = (FIX / "aboki_gbp.html").read_text(encoding="utf-8")
EUR = (FIX / "aboki_eur.html").read_text(encoding="utf-8")


class TestParse:
    def test_usd_rate(self):
        rate, _ = parse(USD)
        assert rate == 1397.0

    def test_gbp_rate(self):
        rate, _ = parse(GBP)
        assert rate == 1850.0

    def test_eur_rate(self):
        rate, _ = parse(EUR)
        assert rate == 1587.0

    def test_date_from_h1(self):
        _, observed_at = parse(USD)
        assert observed_at == datetime(2026, 6, 11, tzinfo=UTC)

    def test_no_table_raises(self):
        with pytest.raises(ValueError):
            parse("<html><body>no rates here</body></html>")


def _fetch():
    async def run():
        async with make_client() as client:
            return await AbokiAdapter(client).fetch()

    return asyncio.run(run())


@respx.mock
def test_fetch_all_three():
    respx.get(BASE + PAGES["USD"]).mock(return_value=httpx.Response(200, text=USD))
    respx.get(BASE + PAGES["GBP"]).mock(return_value=httpx.Response(200, text=GBP))
    respx.get(BASE + PAGES["EUR"]).mock(return_value=httpx.Response(200, text=EUR))
    obs = _fetch()
    by_ccy = {o.currency: o for o in obs}
    assert set(by_ccy) == {"USD", "GBP", "EUR"}
    assert by_ccy["USD"].rate == 1397.0
    assert all(o.tier is Tier.AGGREGATOR and o.side is Side.MID for o in obs)
    assert all(o.source == "aboki" for o in obs)


@respx.mock
def test_partial_failure_still_returns():
    # USD ok, GBP 500, EUR ok → adapter returns the two that worked.
    respx.get(BASE + PAGES["USD"]).mock(return_value=httpx.Response(200, text=USD))
    respx.get(BASE + PAGES["GBP"]).mock(return_value=httpx.Response(500))
    respx.get(BASE + PAGES["EUR"]).mock(return_value=httpx.Response(200, text=EUR))
    obs = _fetch()
    assert {o.currency for o in obs} == {"USD", "EUR"}


@respx.mock
def test_all_fail_raises():
    for path in PAGES.values():
        respx.get(BASE + path).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        _fetch()
