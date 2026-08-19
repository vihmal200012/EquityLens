"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import {
  api,
  ApiError,
  DCFAssumptionsInput,
  DCFResponse,
  DCFScenariosResponse,
  DCFSensitivityResponse,
} from "@/lib/api";
import { Card, StatCard } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtCurrency, fmtMoneyFromMillions, fmtPercent } from "@/lib/format";
import SensitivityHeatmap from "@/components/charts/SensitivityHeatmap";
import { setCached } from "@/lib/cache";

const DEFAULTS = {
  revenueGrowthPct: "8,7,6,5,4",
  ebitMarginPct: "28",
  taxRatePct: "21",
  daPctRevenuePct: "3",
  capexPctRevenuePct: "3",
  nwcPctRevenueChangePct: "10",
  waccPct: "9",
  terminalGrowthPct: "2.5",
};

function parsePctList(s: string): number[] {
  return s
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => parseFloat(v) / 100);
}

function toAssumptions(form: typeof DEFAULTS): DCFAssumptionsInput {
  return {
    revenue_growth_rates: parsePctList(form.revenueGrowthPct),
    ebit_margin: parseFloat(form.ebitMarginPct) / 100,
    tax_rate: parseFloat(form.taxRatePct) / 100,
    da_pct_revenue: parseFloat(form.daPctRevenuePct) / 100,
    capex_pct_revenue: parseFloat(form.capexPctRevenuePct) / 100,
    nwc_pct_revenue_change: parseFloat(form.nwcPctRevenueChangePct) / 100,
    wacc: parseFloat(form.waccPct) / 100,
    terminal_growth: parseFloat(form.terminalGrowthPct) / 100,
  };
}

export default function DCFPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();

  const [form, setForm] = useState(DEFAULTS);
  const [result, setResult] = useState<DCFResponse | null>(null);
  const [scenarios, setScenarios] = useState<DCFScenariosResponse | null>(null);
  const [sensitivity, setSensitivity] = useState<DCFSensitivityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"dcf" | "scenarios" | "sensitivity" | null>(null);

  // A failed run must never leave a previous successful result on screen
  // looking like it came from the request that just failed.
  function clearResults() {
    setResult(null);
    setScenarios(null);
    setSensitivity(null);
  }

  function field(key: keyof typeof DEFAULTS, label: string) {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-black/60 dark:text-white/60">{label}</label>
        <input
          value={form[key]}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          className="w-full rounded-md border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
        />
      </div>
    );
  }

  async function runDCF(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading("dcf");
    try {
      const assumptions = toAssumptions(form);
      const res = await api.runDCF(ticker, assumptions);
      setResult(res);
      setCached(ticker, "dcf_result", res);
      setCached(ticker, "dcf_assumptions", assumptions);
    } catch (e) {
      clearResults();
      setError((e as ApiError).message);
    } finally {
      setLoading(null);
    }
  }

  async function runScenarios() {
    setError(null);
    setLoading("scenarios");
    try {
      const assumptions = toAssumptions(form);
      const res = await api.runDCFScenarios(ticker, assumptions);
      setScenarios(res);
      setCached(ticker, "dcf_scenarios", res);
    } catch (e) {
      clearResults();
      setError((e as ApiError).message);
    } finally {
      setLoading(null);
    }
  }

  async function runSensitivity() {
    setError(null);
    setLoading("sensitivity");
    try {
      const assumptions = toAssumptions(form);
      const res = await api.runSensitivity(ticker, assumptions);
      setSensitivity(res);
    } catch (e) {
      clearResults();
      setError((e as ApiError).message);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-4 text-sm font-semibold">DCF Assumptions</h2>
        <form onSubmit={runDCF} className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="col-span-2 sm:col-span-4">
              {field("revenueGrowthPct", "Revenue growth by year, % (comma-separated)")}
            </div>
            {field("ebitMarginPct", "EBIT margin, %")}
            {field("taxRatePct", "Tax rate, %")}
            {field("daPctRevenuePct", "D&A, % of revenue")}
            {field("capexPctRevenuePct", "CapEx, % of revenue")}
            {field("nwcPctRevenueChangePct", "ΔNWC, % of revenue change")}
            {field("waccPct", "WACC, %")}
            {field("terminalGrowthPct", "Terminal growth, %")}
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={loading !== null}
              className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
            >
              {loading === "dcf" ? "Running…" : "Run DCF"}
            </button>
            <button
              type="button"
              onClick={runScenarios}
              disabled={loading !== null}
              className="rounded-md border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/[0.03] disabled:opacity-50 dark:border-white/15 dark:hover:bg-white/[0.05]"
            >
              {loading === "scenarios" ? "Running…" : "Run Bear/Base/Bull Scenarios"}
            </button>
            <button
              type="button"
              onClick={runSensitivity}
              disabled={loading !== null}
              className="rounded-md border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/[0.03] disabled:opacity-50 dark:border-white/15 dark:hover:bg-white/[0.05]"
            >
              {loading === "sensitivity" ? "Running…" : "Run Sensitivity Table"}
            </button>
          </div>
        </form>
      </Card>

      {error ? <ErrorBanner message={error} /> : null}

      {result ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="Implied Share Price" value={fmtCurrency(result.implied_share_price)} />
            <StatCard label="Enterprise Value" value={fmtMoneyFromMillions(result.enterprise_value)} />
            <StatCard label="Equity Value" value={fmtMoneyFromMillions(result.equity_value)} />
            <StatCard label="Sum PV of FCF" value={fmtMoneyFromMillions(result.sum_pv_fcf)} />
            <StatCard label="Terminal Value" value={fmtMoneyFromMillions(result.terminal_value)} />
            <StatCard label="PV of Terminal Value" value={fmtMoneyFromMillions(result.pv_terminal_value)} />
          </div>

          <Card className="overflow-x-auto">
            <h3 className="mb-3 text-sm font-semibold">FCF Build-up by Forecast Year</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/10 dark:border-white/10">
                  {["Year", "Revenue", "EBIT", "NOPAT", "D&A", "CapEx", "ΔNWC", "FCF", "Discount Factor", "PV of FCF"].map(
                    (h) => (
                      <th key={h} className="py-1.5 px-2 text-right font-medium text-black/50 first:text-left dark:text-white/50">
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {result.forecast.map((f) => (
                  <tr key={f.year_index} className="border-b border-black/5 last:border-0 dark:border-white/5">
                    <td className="py-1.5 px-2">Y{f.year_index}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.revenue)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.ebit)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.nopat)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.da)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.capex)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.nwc_change)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.fcf)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{f.discount_factor.toFixed(3)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtMoneyFromMillions(f.pv_fcf)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      ) : null}

      {loading === "scenarios" ? <LoadingState label="Running scenarios…" /> : null}
      {scenarios ? (
        <Card>
          <h3 className="mb-3 text-sm font-semibold">Bear / Base / Bull Scenarios</h3>
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(scenarios.scenarios).map(([name, s]) => (
              <StatCard
                key={name}
                label={name}
                value={fmtCurrency(s.implied_share_price)}
                sub={`EV ${fmtMoneyFromMillions(s.enterprise_value)}`}
              />
            ))}
          </div>
        </Card>
      ) : null}

      {loading === "sensitivity" ? <LoadingState label="Running sensitivity table…" /> : null}
      {sensitivity ? (
        <Card>
          <h3 className="mb-3 text-sm font-semibold">WACC × Terminal Growth Sensitivity</h3>
          <SensitivityHeatmap
            waccValues={sensitivity.wacc_values}
            growthValues={sensitivity.growth_values}
            prices={sensitivity.prices}
            centerPrice={result?.implied_share_price}
          />
        </Card>
      ) : null}

      <p className="text-xs text-black/40 dark:text-white/40">
        Rejected assumption sets (e.g. WACC ≤ terminal growth) return a 422 with the specific reason —{" "}
        {fmtPercent(0.09)} WACC vs {fmtPercent(0.025)} terminal growth is a safe starting point.
      </p>
    </div>
  );
}
