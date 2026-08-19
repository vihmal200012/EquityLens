"use client";

import { FormEvent, useState } from "react";
import { api, ApiError, PortfolioResponse } from "@/lib/api";
import { Card, StatCard } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtNumber, fmtPercent } from "@/lib/format";
import PortfolioChart from "@/components/charts/PortfolioChart";

interface PositionRow {
  ticker: string;
  prices: string;
  weight: string;
}

const DEFAULT_ROWS: PositionRow[] = [
  { ticker: "AAPL", prices: "180,182,179,185,190,188,195,198,201,199", weight: "0.5" },
  { ticker: "MSFT", prices: "310,312,308,315,320,318,325,330,328,335", weight: "0.5" },
];

function parsePrices(s: string): number[] {
  return s
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean)
    .map(Number);
}

export default function PortfolioPage() {
  const [rows, setRows] = useState<PositionRow[]>(DEFAULT_ROWS);
  const [benchmark, setBenchmark] = useState("");
  const [riskFreeRatePct, setRiskFreeRatePct] = useState("2");
  const [result, setResult] = useState<PortfolioResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function updateRow(i: number, patch: Partial<PositionRow>) {
    const next = [...rows];
    next[i] = { ...next[i], ...patch };
    setRows(next);
  }

  function addRow() {
    setRows([...rows, { ticker: "", prices: "", weight: "" }]);
  }

  function removeRow(i: number) {
    setRows(rows.filter((_, idx) => idx !== i));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const prices_by_ticker: Record<string, number[]> = {};
      const weights: Record<string, number> = {};
      let useWeights = true;
      for (const row of rows) {
        if (!row.ticker.trim()) continue;
        prices_by_ticker[row.ticker.trim().toUpperCase()] = parsePrices(row.prices);
        const w = parseFloat(row.weight);
        if (Number.isNaN(w)) useWeights = false;
        else weights[row.ticker.trim().toUpperCase()] = w;
      }
      const benchmark_prices = benchmark.trim() ? parsePrices(benchmark) : undefined;

      const res = await api.analyzePortfolio({
        prices_by_ticker,
        weights: useWeights ? weights : undefined,
        benchmark_prices,
        risk_free_rate_annual: (parseFloat(riskFreeRatePct) || 0) / 100,
      });
      setResult(res);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Portfolio Analytics</h1>
        <p className="mt-1 text-sm text-black/60 dark:text-white/60">
          Enter a price series per position (comma-separated, same length across all positions) to compute
          return, volatility, Sharpe ratio, drawdown, beta, and correlation.
        </p>
      </div>

      <Card className="overflow-x-auto">
        <form onSubmit={submit} className="space-y-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/10 dark:border-white/10">
                <th className="py-1.5 px-2 text-left font-medium text-black/50 dark:text-white/50">Ticker</th>
                <th className="py-1.5 px-2 text-left font-medium text-black/50 dark:text-white/50">
                  Prices (comma-separated)
                </th>
                <th className="py-1.5 px-2 text-left font-medium text-black/50 dark:text-white/50">
                  Weight (0–1, optional)
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-black/5 last:border-0 dark:border-white/5">
                  <td className="py-1 px-2">
                    <input
                      value={row.ticker}
                      onChange={(e) => updateRow(i, { ticker: e.target.value })}
                      className="w-20 rounded-md border border-black/15 bg-transparent px-2 py-1 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
                    />
                  </td>
                  <td className="py-1 px-2">
                    <input
                      value={row.prices}
                      onChange={(e) => updateRow(i, { prices: e.target.value })}
                      className="w-full min-w-[280px] rounded-md border border-black/15 bg-transparent px-2 py-1 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
                    />
                  </td>
                  <td className="py-1 px-2">
                    <input
                      value={row.weight}
                      onChange={(e) => updateRow(i, { weight: e.target.value })}
                      className="w-20 rounded-md border border-black/15 bg-transparent px-2 py-1 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
                    />
                  </td>
                  <td className="py-1 px-2">
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      className="text-xs text-red-600 hover:underline dark:text-red-400"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <button
            type="button"
            onClick={addRow}
            className="rounded-md border border-black/15 px-3 py-1 text-xs font-medium hover:bg-black/[0.03] dark:border-white/15 dark:hover:bg-white/[0.05]"
          >
            + Add position
          </button>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-black/60 dark:text-white/60">
                Benchmark prices (optional, same length, for beta)
              </label>
              <input
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                placeholder="e.g. S&P 500 index closes"
                className="w-full rounded-md border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-black/60 dark:text-white/60">
                Risk-free rate, annual %
              </label>
              <input
                value={riskFreeRatePct}
                onChange={(e) => setRiskFreeRatePct(e.target.value)}
                className="w-full rounded-md border border-black/15 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {loading ? "Analyzing…" : "Analyze Portfolio"}
          </button>
        </form>
      </Card>

      {error ? <ErrorBanner message={error} /> : null}
      {loading ? <LoadingState /> : null}

      {result ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard label="Total Return" value={fmtPercent(result.total_return)} />
            <StatCard label="Annualized Return" value={fmtPercent(result.annualized_return)} />
            <StatCard label="Volatility" value={fmtPercent(result.volatility)} />
            <StatCard label="Sharpe Ratio" value={fmtNumber(result.sharpe_ratio, 2)} />
            <StatCard label="Max Drawdown" value={fmtPercent(result.max_drawdown)} />
            {result.beta !== undefined ? <StatCard label="Beta" value={fmtNumber(result.beta, 2)} /> : null}
          </div>

          <Card>
            <h3 className="mb-3 text-sm font-semibold">Portfolio Value (normalized)</h3>
            <PortfolioChart series={result.portfolio_value_series} color="#2563eb" />
          </Card>

          <Card>
            <h3 className="mb-3 text-sm font-semibold">Drawdown</h3>
            <PortfolioChart series={result.drawdown_series} color="#dc2626" formatAsPercent />
          </Card>

          {result.correlation_matrix ? (
            <Card className="overflow-x-auto">
              <h3 className="mb-3 text-sm font-semibold">Correlation Matrix</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-black/10 dark:border-white/10">
                    <th className="py-1.5 px-2 text-left" />
                    {Object.keys(result.correlation_matrix).map((t) => (
                      <th key={t} className="py-1.5 px-2 text-right font-medium text-black/50 dark:text-white/50">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.correlation_matrix).map(([t, row]) => (
                    <tr key={t} className="border-b border-black/5 last:border-0 dark:border-white/5">
                      <td className="py-1.5 px-2 font-medium">{t}</td>
                      {Object.keys(result.correlation_matrix!).map((t2) => (
                        <td key={t2} className="py-1.5 px-2 text-right tabular-nums">
                          {fmtNumber(row[t2], 2)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
