import { useQuery } from "@tanstack/react-query";
import { api, fmtNaira, fmtPct } from "../lib/api";

export default function ConsensusCard({ currency }: { currency: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["latest", currency],
    queryFn: () => api.latest(currency),
  });

  if (isLoading) return <Panel>Loading latest rates…</Panel>;
  if (isError || !data?.consensus)
    return (
      <Panel>
        No consensus yet for {currency}. The worker writes one on its first run
        — check <span className="font-data">/api/health</span>.
      </Panel>
    );

  const { consensus, official } = data;
  const parallel = consensus.tiers.find((t) => t.tier === "tier1_aggregator");
  const p2p = consensus.tiers.find((t) => t.tier === "tier2_p2p");
  const cbn = official?.rate ?? null;
  const vsCbn = (rate: number) =>
    cbn != null ? ((rate - cbn) / cbn) * 100 : null;

  const tiles = [
    {
      key: "parallel",
      label: "Parallel (survey)",
      rate: parallel?.rate ?? null,
      n: parallel?.n_sources ?? null,
      spread: parallel ? vsCbn(parallel.rate) : null,
    },
    {
      key: "p2p",
      label: "P2P (USDT/NGN)",
      rate: p2p?.rate ?? null,
      n: p2p?.n_sources ?? null,
      spread: p2p ? vsCbn(p2p.rate) : null,
    },
    {
      key: "cbn",
      label: `Official (${official?.source ?? "CBN"})`,
      rate: cbn,
      n: null,
      spread: null,
    },
  ];

  return (
    <section
      aria-label="Latest rates by mechanism"
      className="rounded-lg border border-line bg-ink-2 p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="font-data text-[11px] uppercase tracking-widest text-muted">
          {currency}/NGN · rates by mechanism
        </p>
        <p className="text-xs text-muted">
          confidence{" "}
          <span className="text-brass">
            {Math.round(consensus.confidence * 100)}%
          </span>
          {" · "}
          <time dateTime={consensus.computed_at}>
            {new Date(consensus.computed_at).toLocaleString()}
          </time>
        </p>
      </div>

      <div className="mt-5 grid gap-6 sm:grid-cols-3">
        {tiles.map((t) => (
          <div key={t.key}>
            <p className="font-data text-[11px] uppercase tracking-widest text-muted">
              {t.label}
            </p>
            <p className="font-data mt-1 text-3xl font-semibold text-bone sm:text-4xl">
              {t.rate != null ? fmtNaira(t.rate) : "—"}
            </p>
            <p className="mt-1 h-4 text-xs text-muted">
              {t.spread != null && (
                <span className="text-oxide">{fmtPct(t.spread)} vs CBN</span>
              )}
              {t.n != null && <span> · {t.n} src</span>}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-ink-2 p-6 text-sm text-muted">
      {children}
    </section>
  );
}
