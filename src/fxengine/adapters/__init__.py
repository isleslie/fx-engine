import logging

import httpx

from .aboki import AbokiAdapter
from .base import BaseAdapter, make_client
from .cbn import CBNAdapter
from .generic import GenericSurveyAdapter, registry_adapters
from .luno import LunoAdapter
from .mock import mock_adapters
from .quidax import QuidaxAdapter
from .talentbase import TalentBaseAdapter

log = logging.getLogger("fxengine.adapters")


def live_adapters(client: httpx.AsyncClient) -> list[BaseAdapter]:
    """The wired live sources: CBN anchor + Tier-1 surveys + Tier-2 P2P feeds.

    Tier-1 surveys come from two places: the config-driven registry
    (config/source_registry.yaml → GenericSurveyAdapter, e.g. ngnrates,
    nairatoday) plus the two bespoke modules whose parsing isn't a simple
    homepage scrape (aboki: per-currency pages; talentbase: label-based tables).
    The transaction-based tier is two independent order-book tickers
    (Quidax, Luno), so the P2P sub-consensus is a real pool, not a single quote.

    nairaspot is intentionally absent — its rates render client-side from an
    endpoint its robots.txt disallows, so there is nothing crawlable to scrape.
    """
    adapters: list[BaseAdapter] = [
        CBNAdapter(client),  # official anchor (never a consensus input)
        AbokiAdapter(client),  # tier 1 — bespoke (per-currency pages)
        TalentBaseAdapter(client),  # tier 1 — bespoke (label-based tables)
        QuidaxAdapter(client),  # tier 2 P2P (USDT/NGN)
        LunoAdapter(client),  # tier 2 P2P (USDT/NGN)
    ]
    try:
        adapters.extend(registry_adapters(client))  # tier 1 — config-driven
    except Exception as exc:  # noqa: BLE001 — never let a registry hiccup abort ingest
        log.error("registry adapters unavailable, continuing with bespoke only: %s", exc)
    return adapters


__all__ = [
    "AbokiAdapter",
    "BaseAdapter",
    "CBNAdapter",
    "GenericSurveyAdapter",
    "LunoAdapter",
    "QuidaxAdapter",
    "TalentBaseAdapter",
    "live_adapters",
    "make_client",
    "mock_adapters",
    "registry_adapters",
]
