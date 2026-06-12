# fx-engine

**A consensus engine for Nigeria's parallel FX market.** Since the original reference
(abokiFX) stopped publishing daily rates in 2021, the market fragmented into many
aggregators, each surveying its own dealers — and nobody authoritative reconciles
them. fx-engine treats those aggregators as independent noisy sensors and
reconciles them into a single, confidence-scored estimate of the parallel
naira rate, tracked against the official CBN anchor.

The methodology — not the chart — is the point:

1. **Source adapters** — one per source, each returning normalized observations.
2. **Normalize** — buy/sell collapse to mids; units and currencies aligned.
3. **Outlier rejection** — median + scaled MAD drops stale or fat-fingered sources.
4. **Consensus** — a weighted mean where each source counts by *freshness*
   (exponential decay) × *agreement* (distance from the pack).
5. **Confidence score** — tightness of agreement × source coverage, 0–1, published
   with every estimate alongside per-source divergence.
6. **Spread** — consensus vs the official CBN rate, in ₦ and %, over time.

## Status

Working skeleton, verified end-to-end on **mock sources** (one deliberately wild
mock source proves the outlier-rejection path on every run). Live adapters for the
real source tiers are the next phase — see `docs/sources.md` for the verified
source map and `CLAUDE.md` for the working brief.

## Stack

Python 3.12 · FastAPI · SQLite (WAL, single-writer) · APScheduler · httpx ·
NumPy — React + Vite + TypeScript · TanStack Query · Recharts · Tailwind v4 —
Docker Compose (caddy / web / worker) · GitHub Actions → GHCR → DigitalOcean.

## Run it locally

```bash
# backend
uv sync
uv run python -m fxengine.worker        # terminal 1: ingest loop (mock sources)
uv run uvicorn fxengine.api.app:app --reload   # terminal 2: API on :8000

# frontend
cd frontend && npm install && npm run dev      # terminal 3: dashboard on :5173
```

Tests: `uv run pytest -q` (backend) · `cd frontend && npx vitest run` (frontend).

## API

| Route | Returns |
|---|---|
| `GET /api/rates/latest?currency=USD` | latest consensus + official + spread |
| `GET /api/rates/history?currency=USD&days=30` | merged consensus/official series |
| `GET /api/spread?currency=USD&days=30` | latest + history in one call |
| `GET /api/sources?currency=USD` | per-source mids and divergence vs consensus |
| `GET /api/health` | liveness + last consensus timestamp |

## Honest caveats

Parallel-market figures are survey-based estimates, not official quotes. This is a
personal research tool over already-public data, with a transparent methodology. It
is **not** a rate to transact on and **not** financial advice. Each live source is
only used in line with its terms; rates are estimates with explicit uncertainty.

## License

MIT — see [LICENSE](LICENSE).
