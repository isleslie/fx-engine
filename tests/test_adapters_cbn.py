"""CBN anchor adapter tests. Offline: respx serves the saved JSON fixture;
the parser is also exercised directly. Never hits cbn.gov.ng."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from fxengine.adapters.base import make_client
from fxengine.adapters.cbn import URL, CBNAdapter, parse
from fxengine.models import Side, Tier

FIXTURE = Path(__file__).parent / "fixtures" / "cbn_exchange_rates.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestParse:
    def test_returns_three_majors(self):
        obs = parse(PAYLOAD)
        assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}

    def test_all_official_mid(self):
        for o in parse(PAYLOAD):
            assert o.tier is Tier.OFFICIAL
            assert o.side is Side.MID
            assert o.source == "cbn"

    def test_uses_central_rate_of_latest_date(self):
        # Fixture's latest ratedate is 2026-06-11; USD central there is 1363.3250.
        usd = next(o for o in parse(PAYLOAD) if o.currency == "USD")
        assert usd.rate == pytest.approx(1363.3250)
        assert usd.observed_at.isoformat() == "2026-06-11T00:00:00+00:00"

    def test_ignores_older_date(self):
        # 2026-06-10 USD central (1361.5549) must not win over the newer row.
        usd = next(o for o in parse(PAYLOAD) if o.currency == "USD")
        assert usd.rate != pytest.approx(1361.5549)

    def test_non_major_currencies_dropped(self):
        # Fixture contains EURO/RIYAL/YEN/etc — only the three majors survive.
        assert len(parse(PAYLOAD)) == 3

    def test_empty_payload_raises(self):
        with pytest.raises(ValueError):
            parse([])


async def _fetch():
    async with make_client() as client:
        return await CBNAdapter(client).fetch()


@respx.mock
def test_fetch_against_mocked_endpoint():
    respx.get(URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    obs = asyncio.run(_fetch())
    assert {o.currency for o in obs} == {"USD", "GBP", "EUR"}


@respx.mock
def test_fetch_raises_on_http_error():
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_fetch())
