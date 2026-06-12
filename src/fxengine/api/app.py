"""FastAPI app. Read-only over the SQLite the worker writes.

Run locally: uvicorn fxengine.api.app:app --reload
In Docker the same app also serves the built SPA from /app/static.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from ..config import settings
from ..models import utcnow
from ..storage import Storage
from .schemas import (
    ConsensusOut,
    HealthOut,
    HistoryOut,
    HistoryPoint,
    LatestOut,
    OfficialOut,
    SourceOut,
    SourcesOut,
)

STATIC_DIR = Path(__file__).resolve().parents[3] / "static"


def get_storage(app: FastAPI) -> Storage | None:
    return app.state.storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The worker may not have created the DB yet on first boot; reconnect lazily.
    app.state.storage = None
    _try_connect(app)
    yield
    if app.state.storage:
        app.state.storage.close()


def _try_connect(app: FastAPI) -> Storage | None:
    if app.state.storage is None and Path(settings.db_path).exists():
        app.state.storage = Storage(settings.db_path, read_only=True)
    return app.state.storage


app = FastAPI(title="fx-engine", version="0.1.0", lifespan=lifespan)


def _require_storage() -> Storage:
    storage = _try_connect(app)
    if storage is None:
        raise HTTPException(503, "database not initialised yet — worker has not run")
    return storage


def _ccy(currency: str) -> str:
    c = currency.upper()
    if c not in settings.currencies:
        raise HTTPException(404, f"unknown currency '{currency}' (have {settings.currencies})")
    return c


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    storage = _try_connect(app)
    last = None
    if storage:
        row = storage.latest_consensus(settings.currencies[0])
        last = datetime.fromisoformat(row["computed_at"]) if row else None
    return HealthOut(status="ok", db=storage is not None, last_consensus_at=last)


@app.get("/api/rates/latest", response_model=LatestOut)
def latest(currency: str = Query("USD")) -> LatestOut:
    storage = _require_storage()
    c = _ccy(currency)
    cons_row = storage.latest_consensus(c)
    off_row = storage.latest_official(c)

    consensus = (
        ConsensusOut(
            currency=cons_row["currency"], rate=cons_row["rate"],
            confidence=cons_row["confidence"], n_sources=cons_row["n_sources"],
            n_rejected=cons_row["n_rejected"], dispersion=cons_row["dispersion"],
            computed_at=datetime.fromisoformat(cons_row["computed_at"]),
        ) if cons_row else None
    )
    official = (
        OfficialOut(
            source=off_row["source"], currency=off_row["currency"], rate=off_row["rate"],
            observed_at=datetime.fromisoformat(off_row["observed_at"]),
        ) if off_row else None
    )
    spread_abs = spread_pct = None
    if consensus and official:
        spread_abs = round(consensus.rate - official.rate, 2)
        spread_pct = round(spread_abs / official.rate * 100, 3)
    return LatestOut(consensus=consensus, official=official,
                     spread_abs=spread_abs, spread_pct=spread_pct)


@app.get("/api/rates/history", response_model=HistoryOut)
def history(currency: str = Query("USD"), days: int = Query(30, ge=1, le=365)) -> HistoryOut:
    storage = _require_storage()
    c = _ccy(currency)
    since = utcnow() - timedelta(days=days)

    points: dict[str, HistoryPoint] = {}
    for row in storage.consensus_history(c, since):
        t = row["computed_at"]
        points.setdefault(t, HistoryPoint(t=datetime.fromisoformat(t))).consensus = row["rate"]
    for row in storage.official_history(c, since):
        t = row["observed_at"]
        points.setdefault(t, HistoryPoint(t=datetime.fromisoformat(t))).official = row["rate"]

    ordered = [points[k] for k in sorted(points)]
    return HistoryOut(currency=c, days=days, points=ordered)


@app.get("/api/spread")
def spread(currency: str = Query("USD"), days: int = Query(30, ge=1, le=365)) -> dict:
    """Convenience view: latest spread + the history series for charting."""
    return {
        "latest": latest(currency).model_dump(),
        "history": history(currency, days).model_dump(),
    }


@app.get("/api/sources", response_model=SourcesOut)
def sources(currency: str = Query("USD")) -> SourcesOut:
    storage = _require_storage()
    c = _ccy(currency)
    cons_row = storage.latest_consensus(c)
    cons_rate = cons_row["rate"] if cons_row else None

    out = []
    for row in storage.latest_observations(c):
        divergence = (
            round((row["mid"] - cons_rate) / cons_rate * 100, 3) if cons_rate else None
        )
        out.append(
            SourceOut(
                source=row["source"], tier=row["tier"], mid=round(row["mid"], 2),
                observed_at=datetime.fromisoformat(row["observed_at"]),
                divergence_pct=divergence,
            )
        )
    return SourcesOut(currency=c, consensus=cons_rate, sources=out)


# Serve the built SPA (present in the Docker image; absent in bare dev).
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
