import pytest
from fastapi.testclient import TestClient

from fxengine.config import settings
from fxengine.models import (
    ConsensusRate,
    Observation,
    Side,
    Tier,
    TierConsensus,
    utcnow,
)
from fxengine.storage import Storage


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setattr(settings, "db_path", db_path)

    storage = Storage(db_path)
    now = utcnow()
    storage.insert_observations(
        [
            Observation("aboki", Tier.AGGREGATOR, "USD", Side.BUY, 1490.0, now),
            Observation("aboki", Tier.AGGREGATOR, "USD", Side.SELL, 1510.0, now),
            Observation("p2p", Tier.P2P, "USD", Side.MID, 1505.0, now),
        ],
        ingested_at=now,
    )
    storage.insert_official(
        [Observation("cbn", Tier.OFFICIAL, "USD", Side.MID, 1410.0, now)], ingested_at=now
    )
    storage.insert_consensus(
        ConsensusRate(
            "USD", 1502.0, 0.92, 2, 1, 0.001, now,
            inter_tier_spread_pct=0.33,
            tiers=(
                TierConsensus(Tier.AGGREGATOR, 1500.0, 1, 0, 0.0, 0.5),
                TierConsensus(Tier.P2P, 1505.0, 1, 1, 0.0, 0.5),
            ),
            rejected_sources=("p2p",),
            correlated_pairs=(("aboki", "p2p"),),
        )
    )
    storage.upsert_reliability("USD", "aboki", 0.8, now)
    storage.close()

    from fxengine.api.app import app

    app.state.storage = None  # force lazy reconnect against the temp DB
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["db"] is True
    assert body["last_consensus_at"] is not None


def test_latest_includes_spread(client):
    body = client.get("/api/rates/latest", params={"currency": "usd"}).json()
    assert body["consensus"]["rate"] == 1502.0
    assert body["official"]["rate"] == 1410.0
    assert body["spread_abs"] == 92.0
    assert body["spread_pct"] == pytest.approx(6.525, abs=0.01)


def test_history_merges_series(client):
    body = client.get("/api/rates/history", params={"currency": "USD", "days": 7}).json()
    assert body["currency"] == "USD"
    assert len(body["points"]) >= 1
    has_consensus = any(p["consensus"] for p in body["points"])
    has_official = any(p["official"] for p in body["points"])
    assert has_consensus and has_official
    # per-tier series present so the chart can plot parallel + p2p separately
    tiers = next((p["tiers"] for p in body["points"] if p["tiers"]), {})
    assert tiers.get("tier1_aggregator") == 1500.0
    assert tiers.get("tier2_p2p") == 1505.0


def test_latest_surfaces_tiers_and_spread(client):
    body = client.get("/api/rates/latest", params={"currency": "USD"}).json()
    cons = body["consensus"]
    assert cons["inter_tier_spread_pct"] == 0.33
    tiers = {t["tier"]: t for t in cons["tiers"]}
    assert set(tiers) == {"tier1_aggregator", "tier2_p2p"}
    assert tiers["tier2_p2p"]["rate"] == 1505.0
    assert tiers["tier1_aggregator"]["weight"] == 0.5


def test_sources_divergence(client):
    body = client.get("/api/sources", params={"currency": "USD"}).json()
    assert body["consensus"] == 1502.0
    sources = {s["source"]: s for s in body["sources"]}
    assert sources["aboki"]["mid"] == 1500.0
    assert sources["aboki"]["divergence_pct"] == pytest.approx(-0.133, abs=0.01)
    # rejected flag mirrors the consensus run's rejected_sources set.
    assert sources["aboki"]["rejected"] is False
    assert sources["p2p"]["rejected"] is True
    # reliability surfaced where a score exists; None for unseen sources.
    assert sources["aboki"]["reliability"] == 0.8
    assert sources["p2p"]["reliability"] is None
    # correlated_with is symmetric across a flagged pair.
    assert sources["aboki"]["correlated_with"] == "p2p"
    assert sources["p2p"]["correlated_with"] == "aboki"


def test_unknown_currency_404(client):
    assert client.get("/api/rates/latest", params={"currency": "ZZZ"}).status_code == 404
