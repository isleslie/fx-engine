import { useQuery } from "@tanstack/react-query";
import { api, fmtNaira, fmtPct } from "../lib/api";

const TIER_LABEL: Record<string, string> = {
  tier1_aggregator: "survey",
  tier2_p2p: "p2p",
  tier3_fintech: "fintech",
};

export default function SourcesTable({ currency }: { currency: string }) {
  const { data } = useQuery({
    queryKey: ["sources", currency],
    queryFn: () => api.sources(currency),
  });

  if (!data || data.sources.length === 0) return null;

  return (
    <section
      aria-label="Source divergence"
      className="rounded-lg border border-line bg-ink-2 p-6"
    >
      <p className="font-data text-[11px] uppercase tracking-widest text-muted">
        Source panel — divergence from consensus
      </p>
      <table className="font-data mt-4 w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-widest text-muted">
            <th className="pb-2 font-normal">Source</th>
            <th className="pb-2 font-normal">Tier</th>
            <th className="pb-2 text-right font-normal">Mid</th>
            <th className="pb-2 text-right font-normal">Divergence</th>
            <th className="pb-2 text-right font-normal">Reliability</th>
            <th className="hidden pb-2 text-right font-normal sm:table-cell">
              Seen
            </th>
          </tr>
        </thead>
        <tbody>
          {data.sources.map((s) => {
            const wide = Math.abs(s.divergence_pct ?? 0) > 2;
            return (
              <tr
                key={s.source}
                className={`border-t border-line ${s.rejected ? "opacity-50" : ""}`}
              >
                <td className="py-2 text-bone">
                  <span className={s.rejected ? "line-through" : ""}>
                    {s.source}
                  </span>
                  {s.rejected && (
                    <span
                      className="ml-2 rounded-sm border border-oxide px-1 text-[10px] uppercase tracking-wider text-oxide"
                      title="Cut as an outlier within its tier this run — excluded from the consensus"
                    >
                      cut
                    </span>
                  )}
                </td>
                <td className="py-2 text-muted">
                  {TIER_LABEL[s.tier] ?? s.tier}
                </td>
                <td className="py-2 text-right text-bone">{fmtNaira(s.mid)}</td>
                <td
                  className={`py-2 text-right ${
                    s.rejected
                      ? "text-muted"
                      : wide
                        ? "text-oxide"
                        : "text-chalk"
                  }`}
                >
                  {s.divergence_pct != null ? fmtPct(s.divergence_pct) : "—"}
                </td>
                <td className="py-2 text-right text-chalk">
                  {s.reliability != null
                    ? `${Math.round(s.reliability * 100)}%`
                    : "—"}
                </td>
                <td className="hidden py-2 text-right text-muted sm:table-cell">
                  {new Date(s.observed_at).toLocaleTimeString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-3 text-[11px] text-muted">
        <span className="text-oxide">Cut</span> = excluded as an outlier within
        its tier; its divergence is shown for reference but did not feed the
        consensus.
      </p>
    </section>
  );
}
