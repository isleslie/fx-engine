import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";

export default function SpreadChart({
  currency,
  days,
}: {
  currency: string;
  days: number;
}) {
  const { data } = useQuery({
    queryKey: ["history", currency, days],
    queryFn: () => api.history(currency, days),
  });

  if (!data || data.points.length === 0) {
    return (
      <section className="rounded-lg border border-line bg-ink-2 p-6 text-sm text-muted">
        History fills in as the worker accumulates runs — the chart appears
        after a few ingest cycles.
      </section>
    );
  }

  const points = data.points.map((p) => ({
    ...p,
    parallel: p.tiers?.tier1_aggregator ?? null,
    p2p: p.tiers?.tier2_p2p ?? null,
    label: new Date(p.t).toLocaleDateString("en-NG", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <section
      aria-label="Consensus vs official history"
      className="rounded-lg border border-line bg-ink-2 p-6"
    >
      <p className="font-data text-[11px] uppercase tracking-widest text-muted">
        Rate by mechanism vs official — last {days} days
      </p>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={points}
            margin={{ top: 4, right: 8, bottom: 0, left: 8 }}
          >
            <CartesianGrid stroke="var(--color-line)" strokeDasharray="2 4" />
            <XAxis
              dataKey="label"
              stroke="var(--color-muted)"
              tick={{ fontSize: 11, fontFamily: "var(--font-data)" }}
              minTickGap={32}
            />
            <YAxis
              stroke="var(--color-muted)"
              tick={{ fontSize: 11, fontFamily: "var(--font-data)" }}
              domain={["auto", "auto"]}
              width={64}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-ink)",
                border: "1px solid var(--color-line)",
                fontFamily: "var(--font-data)",
                fontSize: 12,
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, fontFamily: "var(--font-data)" }}
            />
            <Line
              type="monotone"
              dataKey="parallel"
              name="parallel (survey)"
              stroke="var(--color-brass)"
              dot={false}
              strokeWidth={2}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="p2p"
              name="p2p (USDT/NGN)"
              stroke="var(--color-oxide)"
              dot={false}
              strokeWidth={2}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="consensus"
              name="blended consensus"
              stroke="var(--color-muted)"
              strokeDasharray="4 3"
              dot={false}
              strokeWidth={1.5}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="official"
              name="official (CBN)"
              stroke="var(--color-chalk)"
              dot={false}
              strokeWidth={1.5}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
