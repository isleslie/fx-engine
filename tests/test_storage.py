import sqlite3

from fxengine.models import ConsensusRate, Observation, Side, Tier, TierConsensus, utcnow
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


def test_tier_consensus_persisted_with_blend(tmp_path):
    storage = make_storage(tmp_path)
    now = utcnow()
    c = ConsensusRate(
        "USD", 1442.0, 0.8, 5, 0, 0.001, now,
        inter_tier_spread_pct=-1.5,
        tiers=(
            TierConsensus(Tier.AGGREGATOR, 1450.0, 4, 0, 0.0005, 0.5),
            TierConsensus(Tier.P2P, 1428.0, 1, 0, 0.0, 0.5),
        ),
    )
    storage.insert_consensus(c)
    row = storage.latest_consensus("USD")
    assert row["rate"] == 1442.0
    assert row["inter_tier_spread_pct"] == -1.5
    tiers = {r["tier"]: r for r in storage.latest_tier_consensus("USD")}
    assert set(tiers) == {"tier1_aggregator", "tier2_p2p"}
    assert tiers["tier2_p2p"]["rate"] == 1428.0
    assert tiers["tier1_aggregator"]["weight"] == 0.5
    storage.close()


def test_migration_adds_inter_tier_column_to_legacy_db(tmp_path):
    # Simulate a pre-tier-aware DB: consensus table without the new column.
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE consensus (
            id INTEGER PRIMARY KEY, currency TEXT, rate REAL, confidence REAL,
            n_sources INTEGER, n_rejected INTEGER, dispersion REAL, computed_at TEXT,
            UNIQUE (currency, computed_at)
        );
        """
    )
    conn.execute(
        "INSERT INTO consensus (currency, rate, confidence, n_sources, n_rejected, "
        "dispersion, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("USD", 1400.0, 0.9, 4, 0, 0.001, "2026-06-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    # Opening through Storage must add the column and leave the old row readable.
    storage = Storage(db)
    legacy = storage.latest_consensus("USD")
    assert legacy["rate"] == 1400.0
    assert legacy["inter_tier_spread_pct"] is None  # nullable, old row unaffected
    storage.close()


def test_source_stats_upsert_and_increment(tmp_path):
    storage = make_storage(tmp_path)
    now = utcnow()
    storage.upsert_reliability("USD", "aboki", 0.6, now)
    assert storage.reliability_scores("USD") == {"aboki": 0.6}
    storage.upsert_reliability("USD", "aboki", 0.7, now)  # same key → update + n_runs++
    assert storage.reliability_scores("USD")["aboki"] == 0.7
    row = storage.conn.execute(
        "SELECT n_runs FROM source_stats WHERE source='aboki' AND currency='USD'"
    ).fetchone()
    assert row["n_runs"] == 2
    # scoped per currency
    assert storage.reliability_scores("GBP") == {}
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
