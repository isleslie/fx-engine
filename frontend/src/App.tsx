import { useState } from "react";
import ConsensusCard from "./components/ConsensusCard";
import SensorStrip from "./components/SensorStrip";
import SourcesTable from "./components/SourcesTable";
import SpreadChart from "./components/SpreadChart";

const CURRENCIES = ["USD", "GBP", "EUR"] as const;
const RANGES = [7, 30, 90] as const;

export default function App() {
  const [currency, setCurrency] = useState<string>("USD");
  const [days, setDays] = useState<number>(30);

  return (
    <div className="mx-auto max-w-5xl px-4 pb-16 pt-8 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <h1 className="font-data text-sm font-semibold uppercase tracking-[0.35em] text-brass">
            fx-engine
          </h1>
          <p className="mt-1 max-w-md text-sm text-muted">
            Naira parallel-rate consensus — many noisy sensors, one
            confidence-scored estimate, measured against the official anchor.
          </p>
        </div>
        <nav className="flex gap-6" aria-label="View controls">
          <Toggle
            label="Currency"
            options={CURRENCIES}
            value={currency}
            onChange={(v) => setCurrency(v)}
          />
          <Toggle
            label="Range"
            options={RANGES.map((r) => `${r}d`)}
            value={`${days}d`}
            onChange={(v) => setDays(Number.parseInt(v, 10))}
          />
        </nav>
      </header>

      <main className="mt-8 grid gap-8">
        <ConsensusCard currency={currency} />
        <SensorStrip currency={currency} />
        <SpreadChart currency={currency} days={days} />
        <SourcesTable currency={currency} />
      </main>

      <footer className="mt-12 border-t border-line pt-4 text-xs leading-relaxed text-muted">
        Personal research tool over already-public data. Parallel-market figures
        are survey-based estimates, not official quotes — this is not a rate to
        transact on and not financial advice. Methodology:{" "}
        <span className="font-data">
          tier-aware consensus — survey and P2P mechanisms reconciled separately
          then blended; MAD outlier rejection, freshness × agreement ×
          reliability weighting
        </span>
        .
      </footer>
    </div>
  );
}

function Toggle({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <fieldset>
      <legend className="font-data text-[10px] uppercase tracking-widest text-muted">
        {label}
      </legend>
      <div className="mt-1 flex overflow-hidden rounded border border-line">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            aria-pressed={opt === value}
            className={`font-data px-3 py-1 text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass ${
              opt === value
                ? "bg-brass text-ink"
                : "bg-transparent text-muted hover:text-bone"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
