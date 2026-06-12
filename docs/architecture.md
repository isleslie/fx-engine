# Architecture

Design as agreed in planning (June 2026). Update this file when the methodology or
topology changes — it is the source of truth the README summarizes.

## Topology

One DigitalOcean droplet (`fx-engine`, Ubuntu 24.04, 1 GB), everything in Docker
Compose, total run cost ~$8/mo:

```
                        ┌─────────────────────────────────────────┐
     Internet ─────────▶│ caddy — reverse proxy, automatic HTTPS   │ :80/:443
                        └───────────────┬─────────────────────────┘
                                        │ internal docker network
                        ┌───────────────▼─────────────────┐
                        │ web — FastAPI                    │
                        │  • REST API (/api/*)             │
                        │  • serves the built React SPA    │
                        └───────────────┬──────────────────┘
                                        │ reads (read-only conn)
                                 ┌──────▼──────┐
                                 │   SQLite     │ ◀── bind mount ./data:/data
                                 │   (WAL)      │     (persistent droplet disk)
                                 └──────▲──────┘
                                        │ writes (single writer)
                        ┌───────────────┴──────────────────┐
                        │ worker — APScheduler              │
                        │  every 30–60 min:                 │
                        │   ingest → consensus → store      │
                        └──────┬─────────────┬──────────────┘
                ┌──────────────▼─┐  ┌────────▼─────────┐  ┌──────────────┐
                │ Tier 1 scrapers │  │ Tier 2 P2P feeds │  │ CBN official │
                │ (survey sites)  │  │ (USDT/NGN)       │  │ rate anchor  │
                └─────────────────┘  └──────────────────┘  └──────────────┘
```

Key decisions and the reasons:

- **Droplet over PaaS** — SQLite needs a persistent disk; on App Platform / Railway /
  Vercel the filesystem is ephemeral, forcing a managed Postgres ($15+/mo) and
  blowing the <$10 budget. On a droplet, SQLite-on-disk is free and simple.
- **Single-writer SQLite** — the worker is the only writer; the web tier opens the DB
  read-only. This keeps SQLite's concurrency model comfortable with zero locking
  complexity.
- **Build in CI, never on the box** — 1 GB of RAM can OOM mid-Vite-build. GitHub
  Actions builds a multi-stage image (Node compiles the SPA, output baked into the
  Python image), pushes to GHCR, and the droplet only pulls and restarts. Every
  build is a versioned image, so rollback = redeploy a previous tag.
- **GitOps-lite config** — built images come from GHCR; config (compose + Caddyfile)
  comes from a lightweight git checkout at `~/fx-app` on the droplet.

## Consensus methodology (src/fxengine/engine/)

The defensible-estimate problem: there is no ground truth for the parallel rate —
every source is a survey of the same fuzzy street market. So the engine constructs a
consensus and is honest about its uncertainty.

1. **Normalize** (`normalize.py`) — per source per currency: buy+sell → average;
   single side taken as-is; official-tier observations excluded from the panel.
2. **Outlier rejection** (`outliers.py`) — median + scaled MAD (×1.4826 so `k` reads
   in sigma-like units; default k=3.5). Guards: panels under 3 keep everything;
   MAD=0 falls back to a 1% relative band; rejection never leaves fewer than 2
   survivors.
3. **Weighted consensus** (`consensus.py`) — weight = freshness × agreement, where
   freshness = 0.5^(age_minutes / 90) and agreement = 1/(1+z), z the scaled-MAD
   distance from the median. Stale or straggling sources count less without being
   silently dropped.
4. **Confidence** — sqrt(tightness × coverage): tightness fades linearly to zero as
   relative dispersion reaches 2%; coverage saturates at 6 surviving sources.
   Published with every estimate, alongside per-source divergence, so "high
   confidence, tightly clustered" vs "wide disagreement, treat with caution" is
   always visible.
5. **Spread** — consensus minus the CBN official anchor, absolute and %, stored as
   history for charting.

Tuning lives in `config.py` (`FX_MAD_K`, `FX_FRESHNESS_HALF_LIFE_MINUTES`).

## Data model (SQLite)

- `observations(source, tier, currency, side, rate, observed_at, ingested_at)` —
  raw audit trail, UNIQUE(source, currency, side, observed_at).
- `consensus(currency, rate, confidence, n_sources, n_rejected, dispersion,
  computed_at)` — engine output per run, UNIQUE(currency, computed_at).
- `official(source, currency, rate, observed_at, ingested_at)` — the CBN anchor
  series, kept apart from market observations.

All writes are `INSERT OR IGNORE` against those UNIQUE keys, so re-runs are
idempotent (NGX discipline carried over).

## API ↔ frontend contract

Pydantic models in `src/fxengine/api/schemas.py` are mirrored 1:1 by the TypeScript
types in `frontend/src/lib/api.ts`. Treat them as one artifact.

## Deploy pipeline

`push to main` → deploy.yml: pytest → docker build (multi-stage) → push
`ghcr.io/<owner>/fx-engine:{latest,sha}` → SSH (dedicated CI key) →
`cd ~/fx-app && git pull --ff-only && docker compose pull && docker compose up -d`.

Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`. ci.yml runs lint + both
test suites + a frontend build on every push/PR.

## Risk register

- **Regulatory** — parallel-rate publication is sensitive (CBN/abokiFX history).
  Mitigation: personal research framing, no public rate service, transparent
  methodology, disclaimers in UI and README.
- **Source fragility** — survey sites change markup without notice. Mitigation:
  per-adapter isolation, fixtures + tests per parser, divergence/freshness surfaced
  in the UI, consensus degrades gracefully as sources drop.
- **ToS** — each live adapter checks robots.txt/ToS before being wired; prefer
  documented endpoints where they exist.
