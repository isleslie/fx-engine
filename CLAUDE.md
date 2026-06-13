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
- ✅ DEPLOYED and live (since 2026-06-12): worker ingests every 30 min on the
  droplet; production compose defaults `FX_USE_MOCK_SOURCES=false` (code default
  stays `true` for offline local runs). Serving HTTP on the bare IP
  (`SITE_ADDRESS=:80`). Every push to main auto-deploys.
- ✅ Live panel (7 sources): CBN anchor (JSON API); Tier-1 surveys aboki +
  talentbase (bespoke) and ngnrates + nairatoday (config registry); Tier-2
  transaction-based Quidax + Luno (USDT/NGN order-book tickers, USD only).
  nairaspot skipped (client-rendered, robots-disallowed `/api/`). Tier-3 fintech
  verified and skipped — no app publishes its own posted rate (docs/sources.md).
- ✅ v2 methodology retrofit shipped (2026-06-13, PRs #4–#7): tier-aware consensus
  (survey vs transaction-based reconciled separately, then blended), per-source
  reliability EWMA, copycat independence guard, rejection/tier/spread surfaced in
  API + SPA. See the Architecture methodology section.
- ⬜ NEXT — the build-out is mature; remaining work is durability + ops, then let
  it accrue data for the research writeup:
  1. **Backups** (top risk): the SQLite file is the only copy and now holds
     unreconstructable reliability/correlation history. Litestream → B2, or a
     nightly `sqlite3 .backup` offsite.
  2. Domain + HTTPS (set `SITE_ADDRESS`); uptime/staleness monitoring
     (UptimeRobot on `/api/health` + surface "source last seen"); Dependabot.
  3. After weeks of runs: the analysis writeup (reliability trajectories, the
     survey↔P2P gap, copycat findings, whether the 0.5/0.5 tier weights hold).
  Parked/optional: deeper P2P basket via a p2p.army API key (robots/geo block the
  direct P2P endpoints); more currencies (CAD is on every source); fxratetoday.

## Architecture (full design: docs/architecture.md)

```
caddy (TLS) → web (FastAPI, serves built SPA + /api/*) → SQLite (read)
                                   worker (APScheduler) → SQLite (write)
                                   worker ← adapters (Tier 1 scrape, Tier 2 P2P, CBN anchor)
```

- **Single writer rule**: only the worker writes SQLite; the web tier opens read-only.
- DB lives on the droplet's persistent disk via a bind mount (`./data:/data`). It is
  gitignored — this is a VPS deploy, NOT the NGX commit-back pattern.
- Consensus methodology (src/fxengine/engine/) — **tier-aware**: survey and
  transaction-based feeds measure different things, so they're reconciled
  separately then blended, not pooled. Per currency: normalize buy/sell → mids;
  group by tier; **within each tier** reject outliers (median + scaled MAD, k=3.5)
  and take a weighted mid (weight = freshness[half-life 90m] × agreement[1/(1+z)] ×
  reliability[0.5+score/2] × copycat-penalty); blend tier sub-consensuses by
  configurable `tier_weights` (renormalized over present tiers). Confidence =
  within-tier tightness×depth × cross-tier agreement (a lone tier is capped at
  0.7). Per-source **reliability** is a slow EWMA vs the source's own tier; an
  **independence guard** halves copycat survey pairs. **This methodology is the
  project's value — document any change in docs/architecture.md.**

## Stack (decided — don't relitigate without asking)

Python 3.12, httpx (async), BeautifulSoup, NumPy, raw sqlite3 (no ORM), FastAPI +
Pydantic v2, APScheduler, Caddy. Frontend: TypeScript, React + Vite (no Next.js),
TanStack Query, Recharts, Tailwind v4. Tooling: **uv** (Python), npm or pnpm (JS),
**Biome** (lint+format), Ruff, pytest + respx, Vitest.

## Commands

```bash
uv sync                                   # install backend deps
uv run pytest -q                          # backend tests (79)
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

## Live sources (docs/sources.md has the full verification ledger + endpoints)

Assembled in `live_adapters()` (src/fxengine/adapters/__init__.py):
- **Bespoke modules** (custom logic): `cbn.py` (official anchor, JSON
  `/api/GetAllExchangeRates`), `aboki.py` (3 per-currency pages), `talentbase.py`
  (label-based per-currency tables), `quidax.py` + `luno.py` (Tier-2 USDT/NGN
  order-book tickers, USD only).
- **Config registry** (`config/source_registry.yaml` → `generic.py`): ngnrates,
  nairatoday. fxratetoday is present but `enabled: false`.

Adding a source: check robots.txt/ToS first (skip + note any disallow). For a
simple homepage scrape, add a registry YAML entry + `tests/fixtures/<name>.html`
(the parametrized test auto-covers it) — no module. For custom logic, write a
bespoke `BaseAdapter` module + respx tests and register it. Skipped/parked
candidates (with reasons) live in docs/sources.md: nairaspot, monierate, Bybit/
OKX/Bitget/KuCoin P2P (robots/geo), p2p.army (needs API key), Tier-3 fintech.

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
