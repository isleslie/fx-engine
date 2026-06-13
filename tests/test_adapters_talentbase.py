"""talentbase.ng adapter tests. Offline: respx serves the saved homepage."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.talentbase import URL, TalentBaseAdapter, parse
from fxengine.models import Side, Tier, utcnow

HTML = (Path(__file__).parent / "fixtures" / "talentbase.html").read_text(encoding="utf-8")


class TestParse:
    def test_majors_buy_sell(self):
        d = {c: (b, s) for c, b, s in parse(HTML)}
        assert d["USD"] == (1388.0, 1400.0)
        assert d["EUR"] == (1590.0, 1620.0)
        assert d["GBP"] == (1840.0, 1880.0)

    def test_no_tables_returns_empty(self):
        assert parse("<html><title>x</title><body></body></html>") == []


def _fetch():
    async def run():
        async with make_client() as client:
            return await TalentBaseAdapter(client).fetch()

    return asyncio.run(run())


@respx.mock
def test_fetch_emits_buy_and_sell():
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML))
    obs = _fetch()
    assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}
    gbp = {o.side: o.rate for o in obs if o.currency == "GBP"}
    assert gbp[Side.BUY] == 1840.0 and gbp[Side.SELL] == 1880.0
    assert all(o.tier is Tier.AGGREGATOR and o.source == "talentbase" for o in obs)
    # observed_at is the fetch time (page carries only a date), keeping freshness
    # comparable to the other survey sources rather than a midnight timestamp.
    assert all((utcnow() - o.observed_at).total_seconds() < 60 for o in obs)


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        _fetch()
