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

The defensible-estimate problem: there is no ground truth for the parallel rate.
Worse, the sources are not even measuring the *same* thing — survey aggregators
report street/BDC **cash** quotes, while transaction-based feeds report **USDT/NGN
digital-dollar** clearing prices. These run a persistent gap (transaction-based has
sat ~1.5% below the survey pack). So the engine treats them as distinct
**mechanisms** (tiers), reconciles each on its own, then blends — rather than
pooling everything and letting one mechanism's tight internal agreement masquerade
as ground truth.

1. **Normalize** (`normalize.py`) — per source per currency: buy+sell → average;
   single side taken as-is; official-tier observations excluded from the panel.
2. **Tier-aware reconciliation** (`consensus.py`) — group surviving observations by
   tier (survey aggregators vs transaction-based P2P/exchange), then:
   - **Within-tier outlier rejection** (`outliers.py`) — median + scaled MAD
     (×1.4826 so `k` reads in sigma-like units; default k=3.5; panels under 3 keep
     everything; MAD=0 → 1% relative band; never below 2 survivors). Rejection runs
     **inside each tier only**, so a tight survey pack can never evict the
     transaction-based tier (the single-pool design did exactly that — the lone
     P2P price looked like the outlier against four near-identical surveys and was
     cut every run).
   - **Per-tier sub-consensus** — weight = freshness × agreement, freshness =
     0.5^(age_minutes / 90), agreement = 1/(1+z) with z the scaled-MAD distance
     from the tier median. Stale/straggling sources count less without being
     dropped.
   - **Tier blend** — sub-consensuses combined with configurable
     `tier_weights` (default 0.5 survey / 0.5 P2P), **renormalised over the tiers
     actually present**. A currency with no transaction-based source (GBP/EUR
     today, since the USDT/NGN feeds are USD-only) falls back to survey-only
     cleanly; no special-casing.
3. **Confidence** — rewards *two independent mechanisms agreeing, each with several
   sources*, and caps single-mechanism / single-source reliance:

   ```
   within_quality   = Σ_t weight_t · sqrt(tightness_t × depth_t)
   mechanism_factor = cross-tier agreement   (≥2 tiers present)
                    = SINGLE_TIER_CAP (0.7)   (only one tier present)
   confidence       = within_quality × mechanism_factor
   ```

   Per tier: `tightness` fades to 0 as within-tier relative dispersion reaches 2%;
   `depth` saturates at 3 surviving sources (so a single-source tier is penalised).
   `cross-tier agreement` fades to 0 as the relative spread between tier rates
   reaches 3%. The upshot: one tight mechanism alone is **capped at 0.7** (no
   corroboration), while two mechanisms that genuinely agree can exceed it; a wide
   survey↔P2P gap drives confidence toward 0 ("treat with caution").
4. **Per-source reliability** (`reliability.py`) — a slow EWMA so sources earn
   trust across runs, not within one. After each run, for every participating
   source: `error = |source_mid − tier_sub_consensus| / tier_sub_consensus`
   (a source cut within its tier takes the max, `error = E_MAX = 2%`);
   `quality = max(0, 1 − error/E_MAX)`; `score = (1−α)·score_prev + α·quality`
   with `α = 0.1` and a neutral prior of 0.5. The score feeds back as a
   within-tier weight factor of `(0.5 + score/2)` — a proven source counts up to
   2× an erratic one, but none is ever zeroed. Crucially the comparison is to the
   source's **own tier** sub-consensus, so the structural survey↔P2P gap never
   penalises a source for its mechanism. Scores persist in `source_stats` and are
   surfaced per source via `/api/sources`.
5. **Inter-tier spread** — the signed survey→P2P gap is computed and stored every
   run. It is itself a signal: a stable gap reads as structural (two different
   liquidity pools), a jumpy one as noise. Surfaced so the methodology is honest
   that it reconciles mechanisms by weight rather than averaging them blindly.
6. **Spread vs anchor** — blended consensus minus the CBN official anchor, absolute
   and %, stored as history for charting.

Tuning lives in `config.py` (`FX_MAD_K`, `FX_FRESHNESS_HALF_LIFE_MINUTES`,
`tier_weights`). On weights: 0.5/0.5 is a deliberately neutral starting point. The
transaction-based tier is arguably the higher-quality signal (real clearing prices,
not surveys) and may earn a majority share once the basket is deeper and a learned
per-source reliability weight (a later phase) is in place; until then, neither
mechanism is privileged.

## Data model (SQLite)

- `observations(source, tier, currency, side, rate, observed_at, ingested_at)` —
  raw audit trail, UNIQUE(source, currency, side, observed_at).
- `consensus(currency, rate, confidence, n_sources, n_rejected, dispersion,
  computed_at, inter_tier_spread_pct)` — blended engine output per run,
  UNIQUE(currency, computed_at). `inter_tier_spread_pct` is nullable (None when
  only one tier was present); it was added to the live table via an idempotent
  additive migration (`Storage._migrate`), so pre-tier-aware rows read back fine.
- `tier_consensus(currency, tier, rate, n_sources, n_rejected, dispersion, weight,
  computed_at)` — each mechanism's sub-consensus for a run,
  UNIQUE(currency, tier, computed_at). Joins back to `consensus` on
  (currency, computed_at).
- `official(source, currency, rate, observed_at, ingested_at)` — the CBN anchor
  series, kept apart from market observations.
- `source_stats(source, currency, score, n_runs, updated_at)` — per-source
  reliability EWMA, UNIQUE(source, currency); upserted each run.

All writes are `INSERT OR IGNORE` against those UNIQUE keys, so re-runs are
idempotent (NGX discipline carried over). Schema changes are additive only
(`CREATE TABLE IF NOT EXISTS` / nullable `ADD COLUMN`) — the droplet's live
history must survive every deploy.

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
