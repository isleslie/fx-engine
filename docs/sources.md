# Source map (verified June 2026; implementation status updated after wiring)

The tiers, as researched and verified. Re-check ToS/robots.txt at implementation
time — this landscape shifts. **WIRED** marks adapters implemented and registered in
`live_adapters()`; each has a saved fixture and offline respx tests.

## Anchor (denominator — never a consensus input)

- **CBN NFEM official rate** — **WIRED** (`adapters/cbn.py`). The rates pages are a
  JS shell, but the data behind them is clean JSON at `/api/GetAllExchangeRates`
  (buying/central/selling per currency per date, full history, ~8 MB). We take the
  central rate of the latest `ratedate` for USD/GBP/EUR. robots.txt allows it
  (only `/museum/`, `*.asp$` and a few partials are disallowed).

## Tier 1 — aggregator sites (survey-based "sensors")

All publish daily/hourly parallel rates by surveying dealers. None offers a clean
documented free API for the parallel rate, so each adapter scrapes the displayed
rate. There is no ground truth here; that's why the consensus engine exists.

Tier-1 sources come from two places: the **config-driven registry**
(`config/source_registry.yaml` → `GenericSurveyAdapter`) for simple homepage
scrapes, and **bespoke modules** for sites that need custom logic.

| Source | Status | Notes |
|---|---|---|
| abokiforex.app | **WIRED** — bespoke (`aboki.py`) | One headline rate per currency (no buy/sell), one page each for USD/GBP/EUR; rate from the "1 X to Naira" converter row. Bespoke: fetches three per-currency pages, not one homepage. robots.txt disallows nothing. |
| talentbase.ng | **WIRED** — bespoke (`talentbase.py`) | One table per currency keyed by "(XXX to NGN)", with label-based Buying/Selling rows. Bespoke: label-matching, not positional cells. robots.txt: `Allow: /`. |
| ngnrates.com | **WIRED** — registry | `div.ng-box` cards: ISO in `span.ng-fc`, Black Market row's `span.ng-val` = "buy / sell". Migrated from a module to a YAML entry. robots.txt: `Allow: /`. |
| nairatoday.com | **WIRED** — registry | `table.nt-rates-table` rows (Currency/Buy/Sell/CBN/Change); ISO in parens. Migrated to a YAML entry. robots.txt: `/api/` disallowed (we scrape the page), pages allowed. |
| nairaspot.com | **SKIPPED** | Next.js shell — crawlable HTML carries zero rate values; rates load client-side from `/api/`, which robots.txt disallows. Nothing compliant to scrape. |
| fxratetoday.com | registry entry, `enabled: false` | robots.txt permits (only `/wp-admin/`), but the homepage is a USD-base *international* FX table (decimals like 0.8671 EUR/USD), not a clean NGN parallel survey. No safe generic selector; revisit via its claimed CurrencyRate API. |
| monierate.com | not wired | Prior-art aggregator (its own published spread tracker) rather than a raw dealer survey — ingesting it would be a derived/competitor number, not an independent sensor (same category issue as CoinGecko). Cloudflare content-signals robots.txt. Skip. |

## Tier 2 — transaction-based (USDT/NGN ≈ USD), `Tier.P2P`

Strongest signal (trades actually clearing, not surveys). The 2024 crackdown
reshaped this: Binance suspended all naira services Feb 2024; SEC declared its
operations illegal. 2026 rules require TIN/NIN for *transacting* on licensed
platforms — that governs trading, not reading public market data.

Two grades, kept conceptually distinct (don't pool order-book prices with P2P
offer medians blindly): **Group A** = exchange order-book/ticker (a real clearing
price); **Group B** = P2P marketplaces (one observation = median of top 5–10
sell offers). Both emit `currency="USD"`, `tier=Tier.P2P`.

### Verification ledger (full candidate universe, checked 2026-06-13)

Columns: live-for-NGN · public access route · ToS/robots · decision. "Unreachable"
= connect-timeout/WAF-blocked from the dev box; may differ from the droplet, but
robots/auth/discontinued skips hold everywhere.

| Candidate | Grp | NGN? | Public route | ToS/robots | Decision |
|---|---|---|---|---|---|
| **Quidax** | A | yes | ticker `app.quidax.io/api/v1/markets/tickers/usdtngn` | only blocks `?*attrc=` | **WIRED** (`quidax.py`) — order-book mid (buy+sell)/2 |
| **Luno** | A | yes | ticker `api.luno.com/api/1/ticker?pair=USDTNGN` | `Allow: /`; documented public API | **WIRED** (`luno.py`) — order-book mid (bid+ask)/2, live vol ~658k |
| Busha | A | yes | quotes API only (`/v1/quotes`, POST) | auth (business keys) | skip — no public ticker |
| Roqqu | A | **no** | — | USDT/NGN trading disabled + auth | skip — pair discontinued |
| Bitnob | A | yes | no public rate endpoint found | auth business API | skip — no public data |
| Yellow Card | A/C | yes | `/business/rates` | 401/403 IP-whitelisted | skip — auth-gated |
| Bitmama | A | yes | api host unreachable | — | skip — unreachable |
| BuyCoins (Pro) | A | yes | GraphQL `getPrices` | auth (verified-user keys) | skip — auth-gated |
| Bybit P2P | B | yes | `api2.bybit.com` web endpoint | `robots: Disallow: /` | skip — robots forbids |
| Binance P2P | B | **no** | `/bapi/...` | robots `Disallow: /bapi/`; NGN `total:0` | skip — robots + suspended |
| OKX P2P | B | yes | `/v3/c2c/...` | unverifiable | skip — unreachable here |
| Bitget P2P | B | yes | `/v1/p2p/pub/...` | unverifiable | skip — unreachable here |
| KuCoin P2P | B | yes | `/_api/otc/ad/list` | unverifiable | skip — unreachable here |
| BingX P2P | B | yes | `api-app.bingx.com` | WAF 403 "request blocked" | skip — blocked |
| HTX P2P | B | ? | `otc-api.huobi.pro` | unverifiable | skip — unreachable here |
| Remitano | B | yes | `api.remitano.com` | unverifiable | skip — unreachable here |
| Noones | B | yes | `/rest/v1/offers` (returns JSON) | `robots: Disallow: /rest/` | skip — robots forbids |
| CoinGecko (agg) | E | yes | `/api/v3/simple/price` | `robots: Disallow: /api/v3` | skip — robots forbids |
| **p2p.army** (agg) | E | yes | `/v1/api/*` aggregates 8 P2P venues | `X-APIKEY` required (free tier?) | skip *for now* — needs key |

**Outcome: basket = 2 (Quidax + Luno, both Group A).** Every Group-B/aggregator
route is either robots-disallowed, auth-gated, NGN-discontinued, or unreachable
from the dev environment. Genuine USDT/NGN *order books* live almost only on
Nigerian exchanges; global venues quote NGN only via P2P, whose endpoints are
gated/blocked. USDT≈USD parity assumption documented below.

**Highest-leverage expansion path:** [p2p.army](https://p2p.army/en/api_docs)
with an API key — one adapter would supply Bybit/OKX/Bitget/KuCoin/MEXC/BingX/HTX
NGN medians (Group B) at once. Secondary: re-run the probe from the droplet
(DigitalOcean geo may reach OKX/Bitget/KuCoin/Remitano/HTX where the dev box
times out). If P2P-median sources are added, carry an order-book-vs-median
sub-grade so the two are not weighted identically.

**USDT-parity assumption:** Group A/B sources price USDT/NGN; we treat 1 USDT ≈
1 USD and emit `currency="USD"`. Luno also exposes USDC/NGN but it is illiquid
(wide bid/ask, thin volume) so it is not used. Revisit if USDT depegs materially.

## Tier 3 — fintech / digital BDC published rates (`Tier.FINTECH`) — SKIPPED

A posted buy/sell rate per app, pegged near parallel, would be a *third* mechanism
distinct from surveys and transaction-based feeds. **Verified 2026-06-13 — none
exposes a genuine independent public posted rate, so the tier is skipped** (the
plan's explicit fallback; we do not reverse-engineer app internals).

| Candidate | Finding | Decision |
|---|---|---|
| Monica (monica.cash) | Has a public `/calculator`, but it's **CoinGecko-derived** (market mid refreshed every 60s), not Monica's own off-ramp rate. Non-independent + circular (CoinGecko aggregates the exchanges we already use) — and CoinGecko is itself robots-skipped. | skip — not its own rate |
| Breet, Grey, Raenest/Geegpay | Marketing homepages only; scattered unlabelled numbers, no structured posted rate. The real rate is in-app (auth). | skip — no public rate |
| Cleva | SPA; rate rendered client-side, nothing server-side to read. | skip — client-rendered |
| Dtunes, Lemonade | No public rate page found. | skip |

`tier_weights` already carries a `tier3_fintech` entry as a forward placeholder; it
is inert (no FINTECH source emits, so the tier never appears in a run and is never
in the blend). Revisit if any fintech publishes its *own* posted rate cleanly.

## Tier 4 — Telegram/X BDC channels (noisy, optional)

Skip for v1.

## v1 wiring target — MET (June 2026)

CBN anchor + 4 Tier-1 scrapers + 1 Tier-2 feed are live, exceeding the
"anchor plus ≥3 market sources" bar. Production compose defaults
`FX_USE_MOCK_SOURCES=false`; the code default stays `true` for offline dev.
First real run (2026-06-12): USD consensus 1393.76 from 5 sources (0 rejected,
dispersion 0.001), spread +30.43 NGN (+2.23%) over the CBN anchor; GBP and EUR
landed at +2.23% and +2.26% on 4 sources each (Quidax is USD-only — a Bybit P2P
median would extend transaction-based coverage to GBP/EUR).
