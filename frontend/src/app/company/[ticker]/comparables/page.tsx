"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, ComparablesResponse, PeerInput } from "@/lib/api";
import { Card, StatCard } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtCurrency, fmtNumber } from "@/lib/format";
import { setCached } from "@/lib/cache";

const PEER_FIELDS: { key: keyof PeerInput; label: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: "price", label: "Price" },
  { key: "shares_outstanding", label: "Shares Out (M)" },
  { key: "net_income", label: "Net Income ($M)" },
  { key: "ebitda", label: "EBITDA ($M)" },
  { key: "revenue", label: "Revenue ($M)" },
  { key: "total_debt", label: "Total Debt ($M)" },
  { key: "cash", label: "Cash ($M)" },
  { key: "free_cash_flow", label: "FCF ($M)" },
];

const EXAMPLE_PEERS: PeerInput[] = [
  {
    ticker: "PEER1",
    price: 150,
    shares_outstanding: 1000,
    net_income: 12000,
    ebitda: 20000,
    revenue: 90000,
    total_debt: 15000,
    cash: 10000,
    free_cash_flow: 14000,
  },
  {
    ticker: "PEER2",
    price: 90,
    shares_outstanding: 800,
    net_income: 6000,
    ebitda: 11000,
    revenue: 50000,
    total_debt: 8000,
    cash: 5000,
    free_cash_flow: 7000,
  },
];

export default function ComparablesPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();

  const [peers, setPeers] = useState<PeerInput[]>(EXAMPLE_PEERS);
  const [result, setResult] = useState<ComparablesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function updatePeer(i: number, key: keyof PeerInput, value: string) {
    const next = [...peers];
    next[i] = { ...next[i], [key]: key === "ticker" ? value : parseFloat(value) || 0 };
    setPeers(next);
  }

  function addPeer() {
    setPeers([
      ...peers,
      {
        ticker: "",
        price: 0,
        shares_outstanding: 0,
        net_income: 0,
        ebitda: 0,
        revenue: 0,
        total_debt: 0,
        cash: 0,
        free_cash_flow: 0,
      },
    ]);
  }

  function removePeer(i: number) {
    setPeers(peers.filter((_, idx) => idx !== i));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.runComparables(ticker, peers);
      setResult(res);
      setCached(ticker, "comparables", res);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card className="overflow-x-auto">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Peer Companies</h2>
          <button
            type="button"
            onClick={addPeer}
            className="rounded-md border border-black/15 px-3 py-1 text-xs font-medium hover:bg-black/[0.03] dark:border-white/15 dark:hover:bg-white/[0.05]"
          >
            + Add peer
          </button>
        </div>
        <form onSubmit={submit}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/10 dark:border-white/10">
                {PEER_FIELDS.map((f) => (
                  <th key={f.key} className="py-1.5 px-2 text-left font-medium text-black/50 dark:text-white/50">
                    {f.label}
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {peers.map((peer, i) => (
                <tr key={i} className="border-b border-black/5 last:border-0 dark:border-white/5">
                  {PEER_FIELDS.map((f) => (
                    <td key={f.key} className="py-1 px-2">
                      <input
                        value={peer[f.key] ?? ""}
                        onChange={(e) => updatePeer(i, f.key, e.target.value)}
                        className="w-24 rounded-md border border-black/15 bg-transparent px-2 py-1 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
                      />
                    </td>
                  ))}
                  <td className="py-1 px-2">
                    <button
                      type="button"
                      onClick={() => removePeer(i)}
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
            type="submit"
            disabled={loading || peers.length === 0}
            className="mt-4 rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {loading ? "Running…" : "Run Comparable Analysis"}
          </button>
        </form>
      </Card>

      {error ? <ErrorBanner message={error} /> : null}
      {loading ? <LoadingState /> : null}

      {result ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Implied Price (P/E)"
              value={fmtCurrency(result.implied_price_from_pe)}
              sub={`Median P/E ${fmtNumber(result.median_pe, 1)}x`}
            />
            <StatCard
              label="Implied Price (EV/EBITDA)"
              value={fmtCurrency(result.implied_price_from_ev_ebitda)}
              sub={`Median ${fmtNumber(result.median_ev_ebitda, 1)}x`}
            />
            <StatCard
              label="Implied Price (EV/Revenue)"
              value={fmtCurrency(result.implied_price_from_ev_revenue)}
              sub={`Median ${fmtNumber(result.median_ev_revenue, 1)}x`}
            />
          </div>

          <Card className="overflow-x-auto">
            <h3 className="mb-3 text-sm font-semibold">Peer Multiples</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/10 dark:border-white/10">
                  {["Ticker", "P/E", "EV/EBITDA", "EV/Revenue", "P/S", "FCF Yield"].map((h) => (
                    <th key={h} className="py-1.5 px-2 text-right font-medium text-black/50 first:text-left dark:text-white/50">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.peer_multiples.map((m) => (
                  <tr key={m.ticker} className="border-b border-black/5 last:border-0 dark:border-white/5">
                    <td className="py-1.5 px-2">{m.ticker}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtNumber(m.pe, 1)}x</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtNumber(m.ev_ebitda, 1)}x</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtNumber(m.ev_revenue, 1)}x</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtNumber(m.price_sales, 1)}x</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{fmtNumber((m.fcf_yield ?? 0) * 100, 1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <p className="text-xs text-black/50 dark:text-white/50">{result.methodology_note}</p>
        </div>
      ) : null}
    </div>
  );
}
