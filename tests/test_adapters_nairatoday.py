"""nairatoday.com adapter tests. Offline: respx serves the saved homepage."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.nairatoday import URL, NairaTodayAdapter, parse
from fxengine.models import Side, Tier

HTML = (Path(__file__).parent / "fixtures" / "nairatoday.html").read_text(encoding="utf-8")


class TestParse:
    def test_majors_buy_sell(self):
        rows = {c: (b, s) for c, b, s in parse(HTML)}
        assert rows["USD"] == (1388.0, 1400.0)
        assert rows["GBP"] == (1840.0, 1880.0)
        assert rows["EUR"] == (1590.0, 1620.0)

    def test_iso_code_extracted_from_parens(self):
        codes = {c for c, _, _ in parse(HTML)}
        assert {"USD", "GBP", "EUR"} <= codes

    def test_no_table_raises(self):
        with pytest.raises(ValueError):
            parse("<html><body><p>nothing</p></body></html>")


def _fetch():
    async def run():
        async with make_client() as client:
            return await NairaTodayAdapter(client).fetch()

    return asyncio.run(run())


@respx.mock
def test_fetch_emits_buy_and_sell():
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML))
    obs = _fetch()
    assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}
    usd = {o.side: o.rate for o in obs if o.currency == "USD"}
    assert usd[Side.BUY] == 1388.0 and usd[Side.SELL] == 1400.0
    assert all(o.tier is Tier.AGGREGATOR and o.source == "nairatoday" for o in obs)


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        _fetch()
