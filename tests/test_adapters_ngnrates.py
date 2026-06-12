"""ngnrates.com adapter tests. Offline: respx serves the saved homepage."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.ngnrates import URL, NgnRatesAdapter, parse
from fxengine.models import Side, Tier

HTML = (Path(__file__).parent / "fixtures" / "ngnrates.html").read_text(encoding="utf-8")


class TestParse:
    def test_finds_majors_black_market(self):
        rows = {c: (b, s) for c, b, s in parse(HTML)}
        assert rows["USD"] == (1390.0, 1400.0)
        assert rows["EUR"] == (1595.0, 1640.0)
        assert rows["GBP"] == (1850.0, 1880.0)

    def test_black_market_not_cbn(self):
        # USD black market is 1390/1400; the CBN sub-row (1361.05) must not win.
        usd = next((b, s) for c, b, s in parse(HTML) if c == "USD")
        assert usd == (1390.0, 1400.0)

    def test_also_sees_minor_currencies(self):
        # Parser is generic (returns minors too); the adapter filters later.
        codes = {c for c, _, _ in parse(HTML)}
        assert codes >= {"USD", "GBP", "EUR"}
        assert codes - {"USD", "GBP", "EUR"}  # at least one minor present


def _fetch():
    async def run():
        async with make_client() as client:
            return await NgnRatesAdapter(client).fetch()

    return asyncio.run(run())


@respx.mock
def test_fetch_emits_buy_and_sell_for_majors():
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML))
    obs = _fetch()
    assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}
    usd = {o.side: o.rate for o in obs if o.currency == "USD"}
    assert usd[Side.BUY] == 1390.0 and usd[Side.SELL] == 1400.0
    assert all(o.tier is Tier.AGGREGATOR and o.source == "ngnrates" for o in obs)
    # No minor currencies leak through the adapter filter.
    assert "CAD" not in {o.currency for o in obs}


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(502))
    with pytest.raises(httpx.HTTPStatusError):
        _fetch()
