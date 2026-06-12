import { useQuery } from "@tanstack/react-query";
import { api, fmtNaira } from "../lib/api";

/** The signature element: every sensor plotted as a tick along one rate
 * axis, the consensus as a brass marker. Clustering — the whole story of
 * the methodology — is visible at a glance. */
export default function SensorStrip({ currency }: { currency: string }) {
  const { data } = useQuery({
    queryKey: ["sources", currency],
    queryFn: () => api.sources(currency),
  });

  if (!data || !data.consensus || data.sources.length === 0) return null;

  const mids = data.sources.map((s) => s.mid);
  const lo = Math.min(...mids, data.consensus);
  const hi = Math.max(...mids, data.consensus);
  const pad = (hi - lo) * 0.08 || 1;
  const min = lo - pad;
  const max = hi + pad;
  const x = (v: number) => ((v - min) / (max - min)) * 100;

  return (
    <section
      aria-label="Per-source rate positions"
      className="rounded-lg border border-line bg-ink-2 px-6 pb-4 pt-5"
    >
      <p className="font-data text-[11px] uppercase tracking-widest text-muted">
        Sensor strip — where each source sits
      </p>
      <svg
        viewBox="0 0 100 16"
        preserveAspectRatio="none"
        className="mt-3 h-16 w-full"
        role="img"
        aria-label="Each source's mid rate plotted on a shared axis with the consensus marker"
      >
        <line
          x1="0"
          y1="11"
          x2="100"
          y2="11"
          stroke="var(--color-line)"
          strokeWidth="0.3"
        />
        {data.sources.map((s) => (
          <g key={s.source}>
            <line
              x1={x(s.mid)}
              x2={x(s.mid)}
              y1={Math.abs(s.divergence_pct ?? 0) > 2 ? 5 : 7}
              y2="11"
              stroke={
                Math.abs(s.divergence_pct ?? 0) > 2
                  ? "var(--color-oxide)"
                  : "var(--color-chalk)"
              }
              strokeWidth="0.4"
            />
          </g>
        ))}
        <polygon
          points={`${x(data.consensus)},11 ${x(data.consensus) - 1},14.5 ${x(data.consensus) + 1},14.5`}
          fill="var(--color-brass)"
        />
      </svg>
      <div className="font-data flex justify-between text-[10px] text-muted">
        <span>{fmtNaira(min)}</span>
        <span className="text-brass">consensus {fmtNaira(data.consensus)}</span>
        <span>{fmtNaira(max)}</span>
      </div>
    </section>
  );
}
