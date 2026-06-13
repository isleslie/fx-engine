"""SQLite storage. Same discipline as the NGX repo: idempotent inserts,
WAL mode, the worker is the only writer and the web tier only reads.

Three tables:
- observations: every raw reading from every source (the audit trail)
- consensus:    the engine's output per currency per run
- official:     the CBN anchor series
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import ConsensusRate, Observation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    tier TEXT NOT NULL,
    currency TEXT NOT NULL,
    side TEXT NOT NULL,
    rate REAL NOT NULL,
    observed_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE (source, currency, side, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_obs_ccy_time ON observations (currency, observed_at);

CREATE TABLE IF NOT EXISTS consensus (
    id INTEGER PRIMARY KEY,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    confidence REAL NOT NULL,
    n_sources INTEGER NOT NULL,
    n_rejected INTEGER NOT NULL,
    dispersion REAL NOT NULL,
    computed_at TEXT NOT NULL,
    inter_tier_spread_pct REAL,
    rejected_sources TEXT,
    correlated_pairs TEXT,
    UNIQUE (currency, computed_at)
);
CREATE INDEX IF NOT EXISTS ix_consensus_ccy_time ON consensus (currency, computed_at);

-- Per-tier sub-consensus, one row per (currency, tier, run). Additive: the
-- blended result still lives in `consensus`; this records each mechanism's view.
CREATE TABLE IF NOT EXISTS tier_consensus (
    id INTEGER PRIMARY KEY,
    currency TEXT NOT NULL,
    tier TEXT NOT NULL,
    rate REAL NOT NULL,
    n_sources INTEGER NOT NULL,
    n_rejected INTEGER NOT NULL,
    dispersion REAL NOT NULL,
    weight REAL NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE (currency, tier, computed_at)
);
CREATE INDEX IF NOT EXISTS ix_tier_consensus_ccy_time
    ON tier_consensus (currency, computed_at);

CREATE TABLE IF NOT EXISTS official (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    observed_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE (source, currency, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_official_ccy_time ON official (currency, observed_at);

-- Slow per-source reliability EWMA (one row per source per currency).
CREATE TABLE IF NOT EXISTS source_stats (
    source TEXT NOT NULL,
    currency TEXT NOT NULL,
    score REAL NOT NULL,
    n_runs INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source, currency)
);
"""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class Storage:
    def __init__(self, db_path: Path | str, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        if read_only:
            uri = f"file:{self.db_path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(_SCHEMA)
            self._migrate()
        self.conn.row_factory = sqlite3.Row

    def _migrate(self) -> None:
        """Additive, idempotent upgrades for DBs created before a column existed.

        CREATE TABLE IF NOT EXISTS leaves existing tables untouched, so a column
        added to an existing table needs an explicit guarded ALTER. Production
        history must survive — we only ever ADD nullable columns.
        """
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(consensus)")}
        if "inter_tier_spread_pct" not in cols:
            self.conn.execute("ALTER TABLE consensus ADD COLUMN inter_tier_spread_pct REAL")
        if "rejected_sources" not in cols:
            self.conn.execute("ALTER TABLE consensus ADD COLUMN rejected_sources TEXT")
        if "correlated_pairs" not in cols:
            self.conn.execute("ALTER TABLE consensus ADD COLUMN correlated_pairs TEXT")
        self.conn.commit()

    # ---------- writes (worker only) ----------

    def insert_observations(self, observations: list[Observation], ingested_at: datetime) -> int:
        rows = [
            (o.source, o.tier.value, o.currency, o.side.value, o.rate,
             _iso(o.observed_at), _iso(ingested_at))
            for o in observations
        ]
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO observations "
            "(source, tier, currency, side, rate, observed_at, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return cur.rowcount

    def insert_official(self, observations: list[Observation], ingested_at: datetime) -> int:
        rows = [
            (o.source, o.currency, o.rate, _iso(o.observed_at), _iso(ingested_at))
            for o in observations
        ]
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO official (source, currency, rate, observed_at, ingested_at) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return cur.rowcount

    def insert_consensus(self, c: ConsensusRate) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO consensus "
            "(currency, rate, confidence, n_sources, n_rejected, dispersion, "
            "computed_at, inter_tier_spread_pct, rejected_sources, correlated_pairs) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (c.currency, c.rate, c.confidence, c.n_sources, c.n_rejected,
             c.dispersion, _iso(c.computed_at), c.inter_tier_spread_pct,
             ",".join(c.rejected_sources) or None,
             ",".join(f"{a}|{b}" for a, b in c.correlated_pairs) or None),
        )
        for tc in c.tiers:
            self.conn.execute(
                "INSERT OR IGNORE INTO tier_consensus "
                "(currency, tier, rate, n_sources, n_rejected, dispersion, weight, "
                "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (c.currency, tc.tier.value, tc.rate, tc.n_sources, tc.n_rejected,
                 tc.dispersion, tc.weight, _iso(c.computed_at)),
            )
        self.conn.commit()

    def upsert_reliability(
        self, currency: str, source: str, score: float, updated_at: datetime
    ) -> None:
        """Write a source's new EWMA score, incrementing its run count."""
        self.conn.execute(
            "INSERT INTO source_stats (source, currency, score, n_runs, updated_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(source, currency) DO UPDATE SET "
            "score = excluded.score, n_runs = source_stats.n_runs + 1, "
            "updated_at = excluded.updated_at",
            (source, currency, score, _iso(updated_at)),
        )
        self.conn.commit()

    # ---------- reads (web tier) ----------

    def reliability_scores(self, currency: str) -> dict[str, float]:
        """source -> reliability score for a currency (callers default the rest)."""
        rows = self.conn.execute(
            "SELECT source, score FROM source_stats WHERE currency = ?", (currency,)
        ).fetchall()
        return {r["source"]: r["score"] for r in rows}

    def recent_source_mids(
        self, currency: str, tier: str, n_runs: int
    ) -> dict[str, dict[str, float]]:
        """{source: {run (ingested_at): mid}} over the last n_runs for one tier.

        Mid = mean of that source's readings in the run; used by the independence
        guard to compare survey sources run-over-run.
        """
        rows = self.conn.execute(
            """
            SELECT source, ingested_at, AVG(rate) AS mid
            FROM observations
            WHERE currency = ? AND tier = ? AND ingested_at IN (
                SELECT DISTINCT ingested_at FROM observations
                WHERE currency = ? ORDER BY ingested_at DESC LIMIT ?
            )
            GROUP BY source, ingested_at
            """,
            (currency, tier, currency, n_runs),
        ).fetchall()
        out: dict[str, dict[str, float]] = {}
        for r in rows:
            out.setdefault(r["source"], {})[r["ingested_at"]] = r["mid"]
        return out

    def latest_consensus(self, currency: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM consensus WHERE currency = ? ORDER BY computed_at DESC LIMIT 1",
            (currency,),
        ).fetchone()

    def latest_tier_consensus(self, currency: str) -> list[sqlite3.Row]:
        """Per-tier sub-consensus rows for the most recent run of a currency."""
        return self.conn.execute(
            """
            SELECT * FROM tier_consensus
            WHERE currency = ? AND computed_at = (
                SELECT MAX(computed_at) FROM tier_consensus WHERE currency = ?
            )
            ORDER BY tier
            """,
            (currency, currency),
        ).fetchall()

    def latest_official(self, currency: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM official WHERE currency = ? ORDER BY observed_at DESC LIMIT 1",
            (currency,),
        ).fetchone()

    def consensus_history(self, currency: str, since: datetime) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM consensus WHERE currency = ? AND computed_at >= ? ORDER BY computed_at",
            (currency, _iso(since)),
        ).fetchall()

    def official_history(self, currency: str, since: datetime) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM official WHERE currency = ? AND observed_at >= ? ORDER BY observed_at",
            (currency, _iso(since)),
        ).fetchall()

    def latest_observations(self, currency: str) -> list[sqlite3.Row]:
        """Most recent reading per source for the divergence panel."""
        return self.conn.execute(
            """
            SELECT o.source, o.tier, o.currency,
                   AVG(o.rate) AS mid, MAX(o.observed_at) AS observed_at
            FROM observations o
            JOIN (
                SELECT source, MAX(observed_at) AS latest
                FROM observations WHERE currency = ?
                GROUP BY source
            ) last ON last.source = o.source AND last.latest = o.observed_at
            WHERE o.currency = ?
            GROUP BY o.source
            ORDER BY mid
            """,
            (currency, currency),
        ).fetchall()

    def close(self) -> None:
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass  # read-only connection
        self.conn.close()
