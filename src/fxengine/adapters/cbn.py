"""CBN official rate anchor.

The Central Bank of Nigeria publishes its daily exchange-rate table as JSON at
`/api/GetAllExchangeRates` — buying/central/selling per currency per date, the
same data behind the public "Exchange Rates by Currency" page. This is the
denominator every spread is measured against; it is `Tier.OFFICIAL` and never
enters the market consensus panel.

We take the *central* rate of the most recent `ratedate` for each major as the
official mid. The feed returns full history (thousands of rows across dozens of
currencies); we keep only the latest reading per target currency.

robots.txt (checked 2026-06): `User-agent: * / Allow: /`, with `/api/` not
disallowed. Public government data; read-only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import Observation, Side, Tier
from .base import BaseAdapter

URL = "https://www.cbn.gov.ng/api/GetAllExchangeRates"

# CBN spells currencies out; map the ones we anchor on to ISO codes.
_NAME_TO_ISO = {
    "US DOLLAR": "USD",
    "POUNDS STERLING": "GBP",
    "EURO": "EUR",
}


def parse(payload: list[dict]) -> list[Observation]:
    """Latest central rate per target currency from the CBN rate table."""
    latest: dict[str, dict] = {}
    for row in payload:
        iso = _NAME_TO_ISO.get(str(row.get("currency", "")).strip().upper())
        if iso is None:
            continue
        date = str(row["ratedate"])
        if iso not in latest or date > str(latest[iso]["ratedate"]):
            latest[iso] = row

    observations: list[Observation] = []
    for iso, row in latest.items():
        observed_at = datetime.strptime(row["ratedate"], "%Y-%m-%d").replace(tzinfo=UTC)
        observations.append(
            Observation(
                source="cbn",
                tier=Tier.OFFICIAL,
                currency=iso,
                side=Side.MID,
                rate=float(row["centralrate"]),
                observed_at=observed_at,
            )
        )
    if not observations:
        raise ValueError("CBN feed returned no recognised major currencies")
    return observations


class CBNAdapter(BaseAdapter):
    name = "cbn"
    tier = Tier.OFFICIAL

    async def fetch(self) -> list[Observation]:
        resp = await self.client.get(URL)
        resp.raise_for_status()
        return parse(resp.json())
