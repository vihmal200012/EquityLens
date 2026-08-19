"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, FinancialsResponse } from "@/lib/api";
import { Card } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtBigNumber, titleCase } from "@/lib/format";

const STATEMENTS: { key: "income_statement" | "balance_sheet" | "cash_flow"; label: string }[] = [
  { key: "income_statement", label: "Income Statement" },
  { key: "balance_sheet", label: "Balance Sheet" },
  { key: "cash_flow", label: "Cash Flow Statement" },
];

function Financials({ ticker }: { ticker: string }) {
  const [data, setData] = useState<FinancialsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getFinancials(ticker, 5)
      .then(setData)
      .catch((e: ApiError) => setError(e.message));
  }, [ticker]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <LoadingState />;

  const years = [...data.years].sort((a, b) => a.fiscal_year - b.fiscal_year);

  return (
    <div className="space-y-6">
      {STATEMENTS.map((stmt) => {
        const lineItems = Array.from(
          new Set(years.flatMap((y) => Object.keys(y[stmt.key])))
        );
        return (
          <Card key={stmt.key} className="overflow-x-auto">
            <h2 className="mb-3 text-sm font-semibold">{stmt.label}</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/10 dark:border-white/10">
                  <th className="py-1.5 pr-4 text-left font-medium text-black/50 dark:text-white/50">Line item</th>
                  {years.map((y) => (
                    <th key={y.fiscal_year} className="py-1.5 pl-4 text-right font-medium text-black/50 dark:text-white/50">
                      FY{y.fiscal_year}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lineItems.map((item) => (
                  <tr key={item} className="border-b border-black/5 last:border-0 dark:border-white/5">
                    <td className="py-1.5 pr-4">{titleCase(item)}</td>
                    {years.map((y) => (
                      <td key={y.fiscal_year} className="py-1.5 pl-4 text-right tabular-nums">
                        {fmtBigNumber(y[stmt.key][item])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        );
      })}
    </div>
  );
}

export default function FinancialsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();
  return <Financials key={ticker} ticker={ticker} />;
}
