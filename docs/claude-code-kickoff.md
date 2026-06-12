# Claude Code kickoff prompt

Paste this as your first message in Claude Code, opened at the repo root:

---

Read CLAUDE.md, docs/architecture.md and docs/sources.md before doing anything.

This repo is a verified skeleton: all 24 backend tests and the frontend
lint/test/build pass, and the whole pipeline runs end-to-end on mock sources.
Your job is the live-source phase, in this order:

1. **CBN anchor adapter** (`src/fxengine/adapters/cbn.py`): fetch the official
   USD/GBP/EUR rates from cbn.gov.ng. Save a fixture of the real response under
   tests/fixtures/, write the parser against the fixture, add tests.

2. **Tier-1 adapters**, one at a time, in this order: abokiforex.app,
   nairaspot.com, ngnrates.com, nairatoday.com, talentbase.ng. For each: check
   robots.txt and visible ToS first (skip and note any source that disallows);
   fetch with the shared client from adapters/base.py; save an HTML fixture;
   write the parser against the fixture; add tests. Follow the BaseAdapter
   contract exactly — name, tier, async fetch() -> list[Observation].

3. **One Tier-2 feed**: try Quidax's public ticker first, else a Bybit P2P
   median of top offers. Same fixture+tests discipline.

4. Register the live adapters in worker.get_adapters(), run the worker once
   locally with FX_USE_MOCK_SOURCES=false, and verify a real consensus row
   lands in SQLite and /api/rates/latest serves it.

5. Stop and report: which sources worked, which were skipped (and why), and
   what the first real consensus + spread came out as. Do NOT deploy yet —
   deployment is a separate step we'll do together.

Rules: never hit live sites from tests (respx + fixtures only); keep
api/schemas.py and frontend/src/lib/api.ts in sync if you touch either; run
`uv run pytest -q` and `uv run ruff check src tests` before declaring any step
done.

---
