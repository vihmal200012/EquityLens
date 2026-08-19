"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, DCFScenariosResponse, ReportResponse, SavedReportDetail, SavedReportSummary } from "@/lib/api";
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

  const [savedReports, setSavedReports] = useState<SavedReportSummary[]>([]);
  const [viewingSaved, setViewingSaved] = useState<SavedReportDetail | null>(null);
  const [viewingSavedError, setViewingSavedError] = useState<string | null>(null);

  function refreshSavedReports() {
    api
      .listSavedReports(ticker)
      .then((res) => setSavedReports(res.reports))
      .catch(() => setSavedReports([])); // non-critical: quietly hide the section rather than erroring the page
  }

  useEffect(() => {
    api
      .getQuickReport(ticker)
      .then(setReport)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false));
    refreshSavedReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  async function generateFull() {
    setLoading(true);
    setError(null);
    setViewingSaved(null);
    try {
      // dcf_scenarios is cached as the full /dcf/scenarios response
      // ({ticker, data_mode, scenarios: {bear, base, bull}}) — the report
      // endpoint expects just the inner {bear, base, bull} map, not the
      // whole response, or the scenarios section silently renders empty.
      const scenariosResponse = getCached<DCFScenariosResponse>(ticker, "dcf_scenarios");
      const res = await api.getFullReport(ticker, {
        dcf_result: getCached(ticker, "dcf_result") ?? undefined,
        dcf_assumptions: getCached(ticker, "dcf_assumptions") ?? undefined,
        comparables: getCached(ticker, "comparables") ?? undefined,
        scenarios: scenariosResponse?.scenarios ?? undefined,
      });
      setReport(res);
      refreshSavedReports(); // POST /report just persisted a new row -- pick it up in the list
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  async function viewSavedReport(id: number) {
    setViewingSavedError(null);
    try {
      setViewingSaved(await api.getSavedReport(ticker, id));
    } catch (e) {
      setViewingSavedError((e as ApiError).message);
    }
  }

  const displaying = viewingSaved
    ? {
        title: viewingSaved.title,
        timestampLabel: `Saved ${new Date(viewingSaved.created_at).toLocaleString()}`,
        sections: viewingSaved.sections,
        dataMode: undefined as string | undefined,
      }
    : report
      ? {
          title: report.title,
          timestampLabel: `Generated ${new Date(report.generated_at).toLocaleString()}`,
          sections: report.sections,
          dataMode: report.data_mode as string | undefined,
        }
      : null;

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

      {savedReports.length > 0 ? (
        <Card>
          <h3 className="mb-3 text-sm font-semibold">Saved Reports</h3>
          <ul className="divide-y divide-black/5 dark:divide-white/5">
            {savedReports.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="text-sm font-medium">{r.title}</p>
                  <p className="text-xs text-black/50 dark:text-white/50">
                    {r.generated_by === "ai-research-assistant" ? "AI Q&A" : "Full report"} ·{" "}
                    {new Date(r.created_at).toLocaleString()}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => viewSavedReport(r.id)}
                  className="rounded-md border border-black/15 px-3 py-1 text-xs font-medium hover:bg-black/[0.03] dark:border-white/15 dark:hover:bg-white/[0.05]"
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {error ? <ErrorBanner message={error} /> : null}
      {viewingSavedError ? <ErrorBanner message={viewingSavedError} /> : null}
      {loading && !report ? <LoadingState label="Generating report…" /> : null}

      {viewingSaved ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-black/10 bg-black/[0.02] px-3 py-2 text-xs dark:border-white/10 dark:bg-white/[0.03]">
          <span>Viewing a saved snapshot — not the latest data.</span>
          <button type="button" onClick={() => setViewingSaved(null)} className="font-medium underline">
            Back to latest
          </button>
        </div>
      ) : null}

      {displaying ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold">{displaying.title}</h1>
            {displaying.dataMode ? <DataModeBadge mode={displaying.dataMode} /> : null}
          </div>
          <p className="text-xs text-black/40 dark:text-white/40">{displaying.timestampLabel}</p>

          {Object.entries(displaying.sections).map(([key, content]) => (
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
