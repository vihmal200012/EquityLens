"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, SavedReportSummary } from "@/lib/api";
import { Card } from "@/components/Card";
import { ErrorBanner } from "@/components/StatusStates";
import DataModeBadge from "@/components/DataModeBadge";
import { setCached } from "@/lib/cache";

interface Turn {
  question: string;
  answer?: string;
  dataMode?: string;
  error?: string;
}

export default function AIAssistantPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();

  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<SavedReportSummary[]>([]);

  function refreshHistory() {
    api
      .listSavedReports(ticker)
      .then((res) => setHistory(res.reports.filter((r) => r.generated_by === "ai-research-assistant")))
      .catch(() => setHistory([])); // non-critical: quietly hide the section rather than erroring the page
  }

  useEffect(() => {
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  async function ask(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setQuestion("");
    setLoading(true);
    setTurns((t) => [...t, { question: q }]);
    try {
      const res = await api.askAI(ticker, q);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer: res.answer, dataMode: res.data_mode } : turn)));
      setCached(ticker, "ai_last_answer", res);
      refreshHistory(); // the question was just saved to research_reports -- pick it up
    } catch (e) {
      const message = (e as ApiError).message;
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: message } : turn)));
    } finally {
      setLoading(false);
    }
  }

  async function viewPastQuestion(id: number) {
    try {
      const detail = await api.getSavedReport(ticker, id);
      setTurns((t) => [...t, { question: detail.sections.question, answer: detail.sections.answer }]);
    } catch {
      // non-critical: the "View" button just won't do anything if this fails
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <p className="text-sm text-black/60 dark:text-white/60">
          The assistant answers only from this company&apos;s structured financial context (profile, statements,
          ratios) — never free web search or invented numbers. If <code>AI_API_KEY</code> isn&apos;t configured on
          the backend, this will return a 503.
        </p>
      </Card>

      {history.length > 0 ? (
        <Card>
          <h3 className="mb-3 text-sm font-semibold">Previous Questions</h3>
          <ul className="divide-y divide-black/5 dark:divide-white/5">
            {history.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="text-sm">{h.title.replace(/^AI Q&A: /, "")}</p>
                  <p className="text-xs text-black/50 dark:text-white/50">{new Date(h.created_at).toLocaleString()}</p>
                </div>
                <button
                  type="button"
                  onClick={() => viewPastQuestion(h.id)}
                  className="shrink-0 rounded-md border border-black/15 px-3 py-1 text-xs font-medium hover:bg-black/[0.03] dark:border-white/15 dark:hover:bg-white/[0.05]"
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="space-y-4">
        {turns.map((turn, i) => (
          <Card key={i}>
            <p className="text-sm font-medium">{turn.question}</p>
            {turn.answer ? (
              <>
                <div className="mt-2 flex items-center gap-2">
                  <DataModeBadge mode={turn.dataMode} />
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-black/80 dark:text-white/80">{turn.answer}</p>
              </>
            ) : turn.error ? (
              <div className="mt-2">
                <ErrorBanner message={turn.error} />
              </div>
            ) : (
              <p className="mt-2 text-sm text-black/40 dark:text-white/40">Thinking…</p>
            )}
          </Card>
        ))}
      </div>

      <form onSubmit={ask} className="flex gap-3">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={`Ask about ${ticker}'s financials…`}
          className="flex-1 rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm outline-none focus:border-black/40 dark:border-white/15 dark:focus:border-white/40"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
