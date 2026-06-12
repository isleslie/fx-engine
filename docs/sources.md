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

| Source | Status | Notes |
|---|---|---|
| abokiforex.app | **WIRED** (`aboki.py`) | One headline rate per currency (no buy/sell), one page each for USD/GBP/EUR; rate from the "1 X to Naira" converter row, date from the `<h1>`. robots.txt disallows nothing. Partial page failures tolerated. |
| nairatoday.com | **WIRED** (`nairatoday.py`) | Homepage server-renders `table.nt-rates-table` (Currency/Buy/Sell/CBN/Change); ISO code in parens. robots.txt: `/api/` disallowed, pages allowed, crawl-delay 1. |
| nairaspot.com | **SKIPPED** | Next.js shell — crawlable HTML carries zero rate values; rates load client-side from `/api/`, which robots.txt disallows. Nothing compliant to scrape. Re-check if they ever server-render. |
| ngnrates.com | **WIRED** (`ngnrates.py`) | Homepage `div.ng-box` cards: ISO in `span.ng-fc`, Black Market row's `span.ng-val` = "buy / sell". robots.txt: `Allow: /`. |
| talentbase.ng | **WIRED** (`talentbase.py`) | Homepage has one table per currency with Buying/Selling Rate rows; quote date in the `<title>`. robots.txt: `Allow: /`. |
| fxratetoday.com | not wired | Bonus sensor; claims a "CurrencyRate" API. |
| monierate.com | not wired | Bonus sensor + prior art — already markets an official-vs-parallel spread tracker. Differentiation must be the consensus methodology. |

## Tier 2 — P2P crypto / local exchanges (USDT/NGN ≈ USD)

Strongest transaction-based signal (trades actually clearing, not surveys). The
2024 crackdown reshaped this: Binance suspended all naira services Feb 2024; SEC
declared its operations illegal. 2026 rules require TIN/NIN for transacting on
licensed platforms — that governs trading, not reading public market data.

| Source | Status | Notes |
|---|---|---|
| Quidax | **WIRED** (`quidax.py`) | Public ticker confirmed: `GET app.quidax.io/api/v1/markets/tickers/usdtngn` → buy/sell/last + unix `at`. We use the order-book mid ((buy+sell)/2) as a USD MID observation. robots.txt only blocks `?*attrc=` URLs. |
| Busha | not wired | SEC-aligned, direct naira deposits/withdrawals; candidate public price endpoint. |
| Bybit P2P | not wired | Active NGN P2P marketplace (post-Binance growth); ad listings queryable → best-offer book, take median of top offers. Next candidate if a second Tier-2 signal is wanted. |
| Bitget P2P | not wired | NGN P2P, bank-transfer rail; secondary. |
| KuCoin / MEXC | not wired | P2P via vetted merchants; secondary. |

Play: order-book mid from Quidax/Busha and/or median of top Bybit P2P offers.
Read-only market data only; respect each platform's API terms.

## Tier 3 — fintech / digital BDC published rates (hold for later)

Real but hardest to access cleanly: rates live inside apps (Grey, Raenest/Geegpay,
Cleva; OTC apps like Yellow Card, Breet, Monica, Dtunes). Few public endpoints;
reverse-engineering app-internal APIs is ToS-sensitive. Optional enrichment only —
wire only platforms with a public rate page.

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
