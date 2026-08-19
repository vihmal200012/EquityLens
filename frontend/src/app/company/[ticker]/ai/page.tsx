"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
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
    } catch (e) {
      const message = (e as ApiError).message;
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: message } : turn)));
    } finally {
      setLoading(false);
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
