# Source map (verified June 2026)

The tiers, as researched and verified. Re-check ToS/robots.txt at implementation
time — this landscape shifts.

## Anchor (denominator — never a consensus input)

- **CBN NFEM official rate** — cbn.gov.ng, daily official rates with Excel export.
  Authoritative and free. Every spread is computed against this.

## Tier 1 — aggregator sites (survey-based "sensors")

All publish daily/hourly parallel rates by surveying dealers. None offers a clean
documented free API for the parallel rate, so each adapter scrapes the displayed
rate. There is no ground truth here; that's why the consensus engine exists.

| Source | Notes |
|---|---|
| abokiforex.app | Broadest coverage (USD, GBP, EUR, AED, CAD, ZAR, CNY, AUD, GHS, XOF/XAF), hourly. States it's information-only. |
| nairatoday.com | USD/GBP/EUR/CAD buy/sell + CBN rate + % change; CSV history. Advertised API covers WU/Moneygram + crypto, not clearly the parallel rate — scrape the page. |
| nairaspot.com | CBN official vs parallel for majors, hourly. |
| ngnrates.com | Buy/sell with changes, charts, dealer board. |
| talentbase.ng | Daily buy/sell quoted across Lagos/Abuja/Kano/PH. |
| fxratetoday.com | Bonus sensor; claims a "CurrencyRate" API. |
| monierate.com | Bonus sensor + prior art — already markets an official-vs-parallel spread tracker. Differentiation must be the consensus methodology. |

## Tier 2 — P2P crypto / local exchanges (USDT/NGN ≈ USD)

Strongest transaction-based signal (trades actually clearing, not surveys). The
2024 crackdown reshaped this: Binance suspended all naira services Feb 2024; SEC
declared its operations illegal. 2026 rules require TIN/NIN for transacting on
licensed platforms — that governs trading, not reading public market data.

| Source | Notes |
|---|---|
| Quidax | Cleanest signal: full SEC VASP licence, direct NGN order book. Check for a public ticker API. |
| Busha | SEC-aligned, direct naira deposits/withdrawals; candidate public price endpoint. |
| Bybit P2P | Active NGN P2P marketplace (post-Binance growth); ad listings queryable → best-offer book, take median of top offers. |
| Bitget P2P | NGN P2P, bank-transfer rail; secondary. |
| KuCoin / MEXC | P2P via vetted merchants; secondary. |

Play: order-book mid from Quidax/Busha and/or median of top Bybit P2P offers.
Read-only market data only; respect each platform's API terms.

## Tier 3 — fintech / digital BDC published rates (hold for later)

Real but hardest to access cleanly: rates live inside apps (Grey, Raenest/Geegpay,
Cleva; OTC apps like Yellow Card, Breet, Monica, Dtunes). Few public endpoints;
reverse-engineering app-internal APIs is ToS-sensitive. Optional enrichment only —
wire only platforms with a public rate page.

## Tier 4 — Telegram/X BDC channels (noisy, optional)

Skip for v1.

## v1 wiring target

CBN anchor + 3–5 Tier-1 scrapers + 1–2 Tier-2 feeds → outlier rejection →
confidence-weighted consensus → spread vs CBN. Flip `FX_USE_MOCK_SOURCES=false`
once the anchor plus ≥3 market sources are live.
