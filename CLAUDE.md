# fx-engine

Naira parallel-rate **consensus engine**: many noisy survey-based FX sources in, one
confidence-scored estimate out, measured against the official CBN anchor. Personal
research/portfolio project — explicitly **not** a public rate service, not a rate to
transact on, not financial advice (the CBN has treated parallel-rate publication as
sensitive; keep that framing in all user-facing copy).

## Current status

- ✅ Full skeleton scaffolded and verified: engine + storage + worker + API + SPA all
  pass tests and run end-to-end **on mock sources** (`FX_USE_MOCK_SOURCES=true`).
- ✅ Droplet provisioned: DigitalOcean `fx-engine` (Ubuntu 24.04, 1GB), `deploy` user,
  Cloud Firewall 22/80/443, Docker + Compose installed.
- ✅ Live adapters wired and verified (June 2026): CBN anchor (JSON API) + 4 Tier-1
  (aboki, ngnrates, nairatoday, talentbase) + Quidax USDT/NGN ticker (Tier-2).
  nairaspot skipped — rates render client-side from a robots-disallowed `/api/`.
  First real run: USD consensus 1393.76, +2.23% over CBN, confidence 0.89.
  Production compose now defaults `FX_USE_MOCK_SOURCES=false`; the code default
  stays `true` so bare local runs stay offline-friendly.
- ✅ DEPLOYED (2026-06-12): PR #1 merge auto-deployed to the droplet — secrets and
  the `~/fx-app` bootstrap were already in place, so the pipeline ran end to end.
  The worker ingests live sources every 30 min; the mock-era DB was wiped once
  post-deploy so history is clean. Serving HTTP on the bare IP (`SITE_ADDRESS=:80`).
- ⬜ NEXT (pick up any of): point a domain at the droplet and set `SITE_ADDRESS`
  in `~/fx-app/.env` for automatic HTTPS; extend Tier-2 beyond USD (Bybit P2P
  median would cover GBP/EUR); bonus Tier-1 sensors (fxratetoday, monierate).

## Architecture (full design: docs/architecture.md)

```
caddy (TLS) → web (FastAPI, serves built SPA + /api/*) → SQLite (read)
                                   worker (APScheduler) → SQLite (write)
                                   worker ← adapters (Tier 1 scrape, Tier 2 P2P, CBN anchor)
```

- **Single writer rule**: only the worker writes SQLite; the web tier opens read-only.
- DB lives on the droplet's persistent disk via a bind mount (`./data:/data`). It is
  gitignored — this is a VPS deploy, NOT the NGX commit-back pattern.
- Consensus methodology (src/fxengine/engine/): normalize buy/sell → per-source mids;
  outlier rejection = median + scaled MAD (k=3.5, with zero-MAD relative-tolerance
  fallback and a never-below-2-survivors floor); consensus = weighted mean with
  freshness (exp half-life 90min) × agreement (1/(1+z)) weights; confidence =
  sqrt(tightness × coverage). **This methodology is the project's value — document any
  change in docs/architecture.md.**

## Stack (decided — don't relitigate without asking)

Python 3.12, httpx (async), BeautifulSoup, NumPy, raw sqlite3 (no ORM), FastAPI +
Pydantic v2, APScheduler, Caddy. Frontend: TypeScript, React + Vite (no Next.js),
TanStack Query, Recharts, Tailwind v4. Tooling: **uv** (Python), npm or pnpm (JS),
**Biome** (lint+format), Ruff, pytest + respx, Vitest.

## Commands

```bash
uv sync                                   # install backend deps
uv run pytest -q                          # backend tests (60)
uv run python -m fxengine.worker          # run worker (mock sources by default)
uv run uvicorn fxengine.api.app:app --reload   # API on :8000
cd frontend && npm install && npm run dev      # SPA on :5173, proxies /api → :8000
cd frontend && npx biome check src && npx vitest run && npm run build
```

Config is env-driven via `FX_*` vars (src/fxengine/config.py). Key ones:
`FX_DB_PATH`, `FX_USE_MOCK_SOURCES`, `FX_INGEST_INTERVAL_MINUTES`.

## Conventions

- Adapter contract: subclass `BaseAdapter` (src/fxengine/adapters/base.py), set
  `name` + `tier`, implement `async fetch() -> list[Observation]`. Raise on failure —
  the worker isolates per-adapter errors. One module per source.
- Simple Tier-1 survey scrapes are config-driven: add a YAML entry in
  `config/source_registry.yaml` (consumed by `adapters/generic.py`) with a
  fixture in tests/fixtures/<name>.html — no module needed. Bespoke modules are
  only for sources needing custom logic (aboki: multi-page; talentbase: tables).
  The registry ships in the Docker image (`COPY config/`, `FX_SOURCE_REGISTRY`).
- API schemas (src/fxengine/api/schemas.py) and frontend types
  (frontend/src/lib/api.ts) mirror 1:1 — change them together.
- Tests offline: mock HTTP with respx + saved HTML fixtures in tests/fixtures/
  (same pattern as the NGX repo). Never hit live sites in tests.
- Idempotent inserts everywhere (`INSERT OR IGNORE` + UNIQUE constraints).

## Live sources (wired June 2026 — docs/sources.md has endpoint details)

Registered in `live_adapters()` (src/fxengine/adapters/__init__.py), one module per
source: `cbn.py` (official anchor, JSON `/api/GetAllExchangeRates`), `aboki.py`
(3 per-currency pages), `ngnrates.py`, `nairatoday.py`, `talentbase.py` (homepage
scrapes), `quidax.py` (USDT/NGN public ticker, USD only). nairaspot.com was skipped:
its Next.js pages carry no rates server-side and the data API is robots-disallowed.

Adding a source: check robots.txt/ToS first (skip and note any disallow), fetch
politely (shared client already sets UA + timeout), save a real-response fixture in
tests/fixtures/, write the parser against the fixture, add respx tests, register in
`live_adapters()`. Candidates not yet wired: fxratetoday, monierate (Tier 1);
Busha, Bybit P2P median (Tier 2 — would give GBP/EUR a transaction-based signal too).

## Deploy

Push to main → .github/workflows/deploy.yml: pytest → Docker build (multi-stage:
Node builds SPA into the Python image) → push GHCR → SSH to droplet →
`docker compose pull && up -d`. **Every push to main deploys** — batch doc-only
changes with real ones where convenient.

Already configured (no setup left): repo secrets `DEPLOY_HOST`, `DEPLOY_USER`
(=deploy), `DEPLOY_SSH_KEY` (dedicated CI keypair — NOT the personal key), and the
one-time droplet bootstrap (repo clone at `~/fx-app`, `.env` with `GHCR_IMAGE`).
Rollback = redeploy a previous image tag. Set `SITE_ADDRESS` in `~/fx-app/.env`
once a domain points at the droplet (Caddy then gets TLS automatically).
