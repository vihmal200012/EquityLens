"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, ReportResponse } from "@/lib/api";
import { Card } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import DataModeBadge from "@/components/DataModeBadge";
import { titleCase } from "@/lib/format";
import { getCached } from "@/lib/cache";

function hasAnyCachedResult(ticker: string): boolean {
  return Boolean(
    getCached(ticker, "dcf_result") || getCached(ticker, "comparables") || getCached(ticker, "dcf_scenarios")
  );
}

function Report({ ticker }: { ticker: string }) {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasCachedResults] = useState(() => hasAnyCachedResult(ticker));

  useEffect(() => {
    api
      .getQuickReport(ticker)
      .then(setReport)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  async function generateFull() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getFullReport(ticker, {
        dcf_result: getCached(ticker, "dcf_result") ?? undefined,
        dcf_assumptions: getCached(ticker, "dcf_assumptions") ?? undefined,
        comparables: getCached(ticker, "comparables") ?? undefined,
        scenarios: getCached(ticker, "dcf_scenarios") ?? undefined,
      });
      setReport(res);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Investment Research Report</h2>
            <p className="mt-1 text-xs text-black/50 dark:text-white/50">
              {hasCachedResults
                ? "DCF, comparables, and/or scenario results from this session are available — regenerate to include them."
                : "Run DCF, scenarios, or comparables in their tabs first, then regenerate to fold those results in."}
            </p>
          </div>
          <button
            type="button"
            onClick={generateFull}
            disabled={loading}
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {loading ? "Generating…" : "Regenerate with session results"}
          </button>
        </div>
      </Card>

      {error ? <ErrorBanner message={error} /> : null}
      {loading && !report ? <LoadingState label="Generating report…" /> : null}

      {report ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold">{report.title}</h1>
            <DataModeBadge mode={report.data_mode} />
          </div>
          <p className="text-xs text-black/40 dark:text-white/40">
            Generated {new Date(report.generated_at).toLocaleString()}
          </p>

          {Object.entries(report.sections).map(([key, content]) => (
            <Card key={key}>
              <h3 className="mb-2 text-sm font-semibold">{titleCase(key)}</h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-black/80 dark:text-white/80">
                {content}
              </p>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function ReportPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();
  return <Report key={ticker} ticker={ticker} />;
}
