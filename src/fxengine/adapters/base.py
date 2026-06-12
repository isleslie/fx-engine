"""Adapter contract.

One adapter per source. Every adapter — survey scraper, P2P feed, official
anchor — implements `fetch()` and returns `list[Observation]`. A failing
adapter raises; the worker catches per-adapter so one dead source never
aborts an ingest run.

Live adapters (Claude Code phase) go in this package, one module per source:
    aboki.py, nairatoday.py, nairaspot.py, ngnrates.py, talentbase.py,
    quidax.py, bybit_p2p.py, cbn.py
Each should subclass BaseAdapter, set `name` and `tier`, and implement
`fetch()` using `self.client` (a shared httpx.AsyncClient).
"""

from __future__ import annotations

import abc

import httpx

from ..config import settings
from ..models import Observation, Tier


class BaseAdapter(abc.ABC):
    name: str
    tier: Tier

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @abc.abstractmethod
    async def fetch(self) -> list[Observation]:
        """Return current observations for this source. Raise on failure."""


def make_client() -> httpx.AsyncClient:
    """Shared client: one place for timeout, headers, redirects."""
    return httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )
