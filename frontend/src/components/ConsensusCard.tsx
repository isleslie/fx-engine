import { useQuery } from "@tanstack/react-query";
import { api, fmtNaira, fmtPct } from "../lib/api";

const TIER_LABEL: Record<string, string> = {
  tier1_aggregator: "survey",
  tier2_p2p: "p2p",
  tier3_fintech: "fintech",
};

export default function ConsensusCard({ currency }: { currency: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["latest", currency],
    queryFn: () => api.latest(currency),
  });

  if (isLoading) return <Panel>Loading latest consensus…</Panel>;
  if (isError || !data?.consensus)
    return (
      <Panel>
        No consensus yet for {currency}. The worker writes one on its first run
        — check <span className="font-data">/api/health</span>.
      </Panel>
    );

  const { consensus, official, spread_abs, spread_pct } = data;
  const confidencePct = Math.round(consensus.confidence * 100);

  return (
    <section
      aria-label="Latest consensus rate"
      className="grid gap-6 rounded-lg border border-line bg-ink-2 p-6 sm:grid-cols-[1fr_auto]"
    >
      <div>
        <p className="font-data text-[11px] uppercase tracking-widest text-muted">
          Parallel consensus · {currency}/NGN
        </p>
        <p className="font-data mt-2 text-5xl font-semibold text-bone sm:text-6xl">
          {fmtNaira(consensus.rate)}
        </p>
        <p className="mt-3 text-sm text-muted">
          {consensus.n_sources} sources agreed
          {consensus.n_rejected > 0 && (
            <span className="text-oxide">
              {" "}
              · {consensus.n_rejected} rejected as outliers
            </span>
          )}
          {" · "}
          <time dateTime={consensus.computed_at}>
            {new Date(consensus.computed_at).toLocaleString()}
          </time>
        </p>

        {consensus.tiers.length > 1 && (
          <div className="mt-4 border-t border-line pt-3">
            <p className="font-data text-[11px] uppercase tracking-widest text-muted">
              By mechanism
            </p>
            <div className="font-data mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {consensus.tiers.map((t) => (
                <span key={t.tier} className="text-chalk">
                  {TIER_LABEL[t.tier] ?? t.tier}{" "}
                  <span className="text-bone">{fmtNaira(t.rate)}</span>
                  <span className="text-muted">
                    {" "}
                    ·{t.n_sources}src ·w{t.weight.toFixed(2)}
                  </span>
                </span>
              ))}
            </div>
            {consensus.inter_tier_spread_pct != null && (
              <p className="mt-2 text-sm text-muted">
                survey→p2p gap{" "}
                <span className="text-oxide">
                  {fmtPct(consensus.inter_tier_spread_pct)}
                </span>{" "}
                — transaction vs survey pricing
              </p>
            )}
          </div>
        )}
      </div>

      <dl className="grid content-start gap-4 sm:text-right">
        <div>
          <dt className="font-data text-[11px] uppercase tracking-widest text-muted">
            Confidence
          </dt>
          <dd className="font-data text-2xl text-brass">{confidencePct}%</dd>
          <meter
            className="mt-1 h-1 w-32"
            min={0}
            max={100}
            value={confidencePct}
            aria-label={`Confidence ${confidencePct} percent`}
          />
        </div>
        {official && spread_abs != null && spread_pct != null && (
          <div>
            <dt className="font-data text-[11px] uppercase tracking-widest text-muted">
              vs official ({official.source})
            </dt>
            <dd className="font-data text-lg text-chalk">
              {fmtNaira(official.rate)}
            </dd>
            <dd className="font-data text-sm text-oxide">
              spread {fmtNaira(spread_abs)} ({fmtPct(spread_pct)})
            </dd>
          </div>
        )}
      </dl>
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
