"""talentbase.ng adapter tests. Offline: respx serves the saved homepage."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.talentbase import URL, TalentBaseAdapter, parse
from fxengine.models import Side, Tier

HTML = (Path(__file__).parent / "fixtures" / "talentbase.html").read_text(encoding="utf-8")


class TestParse:
    def test_majors_buy_sell(self):
        _, rows = parse(HTML)
        d = {c: (b, s) for c, b, s in rows}
        assert d["USD"] == (1388.0, 1400.0)
        assert d["EUR"] == (1590.0, 1620.0)
        assert d["GBP"] == (1840.0, 1880.0)

    def test_observed_at_from_title(self):
        observed_at, _ = parse(HTML)
        assert observed_at == datetime(2026, 6, 12, tzinfo=UTC)

    def test_no_tables_raises_nothing_but_empty(self):
        observed_at, rows = parse("<html><title>x</title><body></body></html>")
        assert rows == []


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
    assert all(o.observed_at == datetime(2026, 6, 12, tzinfo=UTC) for o in obs)


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        _fetch()
