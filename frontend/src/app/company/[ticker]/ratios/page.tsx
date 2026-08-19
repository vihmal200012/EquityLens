"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, RatiosResponse } from "@/lib/api";
import { Card } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtNumber, fmtPercent, titleCase } from "@/lib/format";
import RatioTrendChart from "@/components/charts/RatioTrendChart";

const PERCENT_RATIOS = [
  "revenue_growth",
  "eps_growth",
  "gross_margin",
  "operating_margin",
  "net_margin",
  "ebitda_margin",
  "fcf_margin",
  "roe",
  "roic",
];

function Ratios({ ticker }: { ticker: string }) {
  const [data, setData] = useState<RatiosResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getRatios(ticker, 5)
      .then(setData)
      .catch((e: ApiError) => setError(e.message));
  }, [ticker]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <LoadingState />;

  const years = Object.keys(data.ratios_by_year)
    .map(Number)
    .sort((a, b) => a - b);
  const ratioNames = Array.from(new Set(years.flatMap((y) => Object.keys(data.ratios_by_year[y]))));

  const chartData = years.map((y) => ({ fiscal_year: y, ...data.ratios_by_year[y] }));

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Margin Trend</h2>
        <RatioTrendChart data={chartData} seriesKeys={["gross_margin", "operating_margin", "net_margin"]} />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Growth Trend</h2>
        <RatioTrendChart data={chartData} seriesKeys={["revenue_growth", "eps_growth"]} />
      </Card>

      <Card className="overflow-x-auto">
        <h2 className="mb-3 text-sm font-semibold">All Ratios by Fiscal Year</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-black/10 dark:border-white/10">
              <th className="py-1.5 pr-4 text-left font-medium text-black/50 dark:text-white/50">Ratio</th>
              {years.map((y) => (
                <th key={y} className="py-1.5 pl-4 text-right font-medium text-black/50 dark:text-white/50">
                  FY{y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ratioNames.map((name) => (
              <tr key={name} className="border-b border-black/5 last:border-0 dark:border-white/5">
                <td className="py-1.5 pr-4">{titleCase(name)}</td>
                {years.map((y) => {
                  const v = data.ratios_by_year[y][name];
                  return (
                    <td key={y} className="py-1.5 pl-4 text-right tabular-nums">
                      {PERCENT_RATIOS.includes(name) ? fmtPercent(v) : fmtNumber(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

export default function RatiosPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();
  return <Ratios key={ticker} ticker={ticker} />;
}
