"""Quidax Tier-2 adapter tests. Offline: respx serves the saved ticker JSON."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.quidax import URL, QuidaxAdapter, parse
from fxengine.models import Side, Tier

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "quidax_usdtngn.json").read_text(encoding="utf-8")
)


class TestParse:
    def test_mid_is_buy_sell_average(self):
        obs = parse(PAYLOAD)
        # buy 1386.0, sell 1391.75 → mid 1388.875
        assert obs.rate == pytest.approx(1388.875)

    def test_currency_and_classification(self):
        obs = parse(PAYLOAD)
        assert obs.currency == "USD"
        assert obs.tier is Tier.P2P
        assert obs.side is Side.MID
        assert obs.source == "quidax"

    def test_observed_at_from_unix_timestamp(self):
        obs = parse(PAYLOAD)
        assert obs.observed_at == datetime.fromtimestamp(1781228891, tz=UTC)


def _fetch():
    async def run():
        async with make_client() as client:
            return await QuidaxAdapter(client).fetch()

    return asyncio.run(run())


@respx.mock
def test_fetch_returns_single_usd_mid():
    respx.get(URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    obs = _fetch()
    assert len(obs) == 1
    assert obs[0].currency == "USD" and obs[0].tier is Tier.P2P


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        _fetch()
