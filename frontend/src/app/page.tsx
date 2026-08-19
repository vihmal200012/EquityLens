"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, CompanyListResponse } from "@/lib/api";
import { Card } from "@/components/Card";
import DataModeBadge from "@/components/DataModeBadge";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<CompanyListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ticker, setTicker] = useState("");

  useEffect(() => {
    api
      .listCompanies()
      .then(setData)
      .catch((e: ApiError) => setError(e.message));
  }, []);

  function go(e: FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (t) router.push(`/company/${t}`);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Equity Research Dashboard</h1>
        <p className="mt-1 text-sm text-black/60 dark:text-white/60">
          Financial statements, DCF valuation, comparable-company analysis, and an AI research assistant —
          grounded entirely in structured data.
        </p>
      </div>

      <Card>
        <form onSubmit={go} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[220px]">
            <label className="mb-1 block text-xs font-medium text-black/60 dark:text-white/60">
              Look up a company
            </label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Enter ticker, e.g. AAPL"
              className="w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
            />
          </div>
          <button
            type="submit"
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            View company
          </button>
        </form>
      </Card>

      {error ? <ErrorBanner message={error} /> : null}

      {!data && !error ? <LoadingState label="Loading companies…" /> : null}

      {data ? (
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Available companies</h2>
            <DataModeBadge mode={data.data_mode} />
          </div>
          {data.note ? <p className="mb-3 text-sm text-black/60 dark:text-white/60">{data.note}</p> : null}
          {data.tickers.length === 0 ? (
            <p className="text-sm text-black/50 dark:text-white/50">
              No enumerable ticker list — search by exact ticker above.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {data.tickers.map((t) => (
                <Link
                  key={t}
                  href={`/company/${t}`}
                  className="rounded-full border border-black/15 px-3 py-1.5 text-sm font-medium hover:border-black/40 hover:bg-black/[0.03] dark:border-white/15 dark:hover:border-white/40 dark:hover:bg-white/[0.05]"
                >
                  {t}
                </Link>
              ))}
            </div>
          )}
        </Card>
      ) : null}
    </div>
  );
}
