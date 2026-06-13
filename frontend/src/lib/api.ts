/** Typed fetchers. These types mirror src/fxengine/api/schemas.py 1:1 —
 * change them together. */

export type TierReading = {
  tier: string;
  rate: number;
  n_sources: number;
  n_rejected: number;
  dispersion: number;
  weight: number;
};

export type Consensus = {
  currency: string;
  rate: number;
  confidence: number;
  n_sources: number;
  n_rejected: number;
  dispersion: number;
  computed_at: string;
  inter_tier_spread_pct: number | null;
  tiers: TierReading[];
};

export type Official = {
  source: string;
  currency: string;
  rate: number;
  observed_at: string;
};

export type Latest = {
  consensus: Consensus | null;
  official: Official | null;
  spread_abs: number | null;
  spread_pct: number | null;
};

export type HistoryPoint = {
  t: string;
  consensus: number | null;
  official: number | null;
};

export type History = {
  currency: string;
  days: number;
  points: HistoryPoint[];
};

export type SourceReading = {
  source: string;
  tier: string;
  mid: number;
  observed_at: string;
  divergence_pct: number | null;
  rejected: boolean;
  reliability: number | null;
};

export type Sources = {
  currency: string;
  consensus: number | null;
  sources: SourceReading[];
};

async function get<T>(
  path: string,
  params: Record<string, string>,
): Promise<T> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${path}?${qs}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  latest: (currency: string) => get<Latest>("/api/rates/latest", { currency }),
  history: (currency: string, days: number) =>
    get<History>("/api/rates/history", { currency, days: String(days) }),
  sources: (currency: string) => get<Sources>("/api/sources", { currency }),
};

export const fmtNaira = (value: number): string =>
  `\u20a6${value.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const fmtPct = (value: number): string =>
  `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
