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
            <th className="hidden pb-2 text-right font-normal sm:table-cell">
              Seen
            </th>
          </tr>
        </thead>
        <tbody>
          {data.sources.map((s) => {
            const wide = Math.abs(s.divergence_pct ?? 0) > 2;
            return (
              <tr key={s.source} className="border-t border-line">
                <td className="py-2 text-bone">{s.source}</td>
                <td className="py-2 text-muted">
                  {TIER_LABEL[s.tier] ?? s.tier}
                </td>
                <td className="py-2 text-right text-bone">{fmtNaira(s.mid)}</td>
                <td
                  className={`py-2 text-right ${wide ? "text-oxide" : "text-chalk"}`}
                >
                  {s.divergence_pct != null ? fmtPct(s.divergence_pct) : "—"}
                </td>
                <td className="hidden py-2 text-right text-muted sm:table-cell">
                  {new Date(s.observed_at).toLocaleTimeString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
