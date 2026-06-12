from fxengine.models import ConsensusRate, Observation, Side, Tier, utcnow
from fxengine.storage import Storage


def make_storage(tmp_path):
    return Storage(tmp_path / "test.db")


def test_observation_insert_is_idempotent(tmp_path):
    storage = make_storage(tmp_path)
    now = utcnow()
    obs = [Observation("aboki", Tier.AGGREGATOR, "USD", Side.BUY, 1490.0, now)]
    assert storage.insert_observations(obs, ingested_at=now) == 1
    assert storage.insert_observations(obs, ingested_at=now) == 0  # duplicate ignored
    storage.close()


def test_consensus_roundtrip_and_latest(tmp_path):
    storage = make_storage(tmp_path)
    t1, t2 = utcnow(), utcnow()
    storage.insert_consensus(ConsensusRate("USD", 1500.0, 0.9, 5, 1, 0.001, t1))
    storage.insert_consensus(ConsensusRate("USD", 1510.0, 0.85, 5, 0, 0.002, t2))
    row = storage.latest_consensus("USD")
    assert row["rate"] == 1510.0
    history = storage.consensus_history("USD", since=t1)
    assert len(history) == 2
    storage.close()


def test_official_separate_from_market(tmp_path):
    storage = make_storage(tmp_path)
    now = utcnow()
    storage.insert_official(
        [Observation("cbn", Tier.OFFICIAL, "USD", Side.MID, 1410.0, now)], ingested_at=now
    )
    assert storage.latest_official("USD")["rate"] == 1410.0
    assert storage.latest_consensus("USD") is None
    storage.close()


def test_latest_observations_one_row_per_source(tmp_path):
    storage = make_storage(tmp_path)
    now = utcnow()
    obs = [
        Observation("a", Tier.AGGREGATOR, "USD", Side.BUY, 1490.0, now),
        Observation("a", Tier.AGGREGATOR, "USD", Side.SELL, 1510.0, now),
        Observation("b", Tier.P2P, "USD", Side.MID, 1505.0, now),
    ]
    storage.insert_observations(obs, ingested_at=now)
    rows = storage.latest_observations("USD")
    assert len(rows) == 2
    by_source = {r["source"]: r["mid"] for r in rows}
    assert by_source["a"] == 1500.0  # buy/sell averaged
    assert by_source["b"] == 1505.0
    storage.close()
