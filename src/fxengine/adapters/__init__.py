import httpx

from .aboki import AbokiAdapter
from .base import BaseAdapter, make_client
from .cbn import CBNAdapter
from .mock import mock_adapters
from .nairatoday import NairaTodayAdapter
from .ngnrates import NgnRatesAdapter
from .quidax import QuidaxAdapter
from .talentbase import TalentBaseAdapter


def live_adapters(client: httpx.AsyncClient) -> list[BaseAdapter]:
    """The wired live sources: CBN anchor + Tier-1 surveys + one Tier-2 P2P feed.

    nairaspot is intentionally absent — its rates render client-side from an
    endpoint its robots.txt disallows, so there is nothing crawlable to scrape.
    """
    return [
        CBNAdapter(client),  # official anchor (never a consensus input)
        AbokiAdapter(client),  # tier 1
        NgnRatesAdapter(client),  # tier 1
        NairaTodayAdapter(client),  # tier 1
        TalentBaseAdapter(client),  # tier 1
        QuidaxAdapter(client),  # tier 2 P2P (USDT/NGN)
    ]


__all__ = [
    "AbokiAdapter",
    "BaseAdapter",
    "CBNAdapter",
    "NairaTodayAdapter",
    "NgnRatesAdapter",
    "QuidaxAdapter",
    "TalentBaseAdapter",
    "live_adapters",
    "make_client",
    "mock_adapters",
]
