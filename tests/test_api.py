import pytest
from fastapi.testclient import TestClient

from fxengine.config import settings
from fxengine.models import ConsensusRate, Observation, Side, Tier, utcnow
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
    storage.insert_consensus(ConsensusRate("USD", 1502.0, 0.92, 2, 0, 0.001, now))
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


def test_sources_divergence(client):
    body = client.get("/api/sources", params={"currency": "USD"}).json()
    assert body["consensus"] == 1502.0
    sources = {s["source"]: s for s in body["sources"]}
    assert sources["aboki"]["mid"] == 1500.0
    assert sources["aboki"]["divergence_pct"] == pytest.approx(-0.133, abs=0.01)


def test_unknown_currency_404(client):
    assert client.get("/api/rates/latest", params={"currency": "ZZZ"}).status_code == 404
