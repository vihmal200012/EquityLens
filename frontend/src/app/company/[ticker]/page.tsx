"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, CompanyProfile, RatiosResponse } from "@/lib/api";
import { Card, StatCard } from "@/components/Card";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtPercent } from "@/lib/format";

function Overview({ ticker }: { ticker: string }) {
  const [company, setCompany] = useState<CompanyProfile | null>(null);
  const [ratios, setRatios] = useState<RatiosResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getCompany(ticker), api.getRatios(ticker, 1)])
      .then(([c, r]) => {
        setCompany(c);
        setRatios(r);
      })
      .catch((e: ApiError) => setError(e.message));
  }, [ticker]);

  if (error) return <ErrorBanner message={error} />;
  if (!company) return <LoadingState />;

  const latestYear = ratios ? Math.max(...Object.keys(ratios.ratios_by_year).map(Number)) : null;
  const latest = latestYear !== null ? ratios!.ratios_by_year[latestYear] : null;

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="mb-2 text-sm font-semibold">Company Profile</h2>
        <p className="text-sm leading-relaxed text-black/70 dark:text-white/70">{company.description}</p>
        <p className="mt-3 text-xs text-black/50 dark:text-white/50">
          Shares outstanding: {company.shares_outstanding.toLocaleString()}
        </p>
      </Card>

      {latest ? (
        <div>
          <h2 className="mb-3 text-sm font-semibold">
            Key Ratios {latestYear ? `(FY${latestYear})` : ""}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <StatCard label="Revenue Growth" value={fmtPercent(latest.revenue_growth)} />
            <StatCard label="Gross Margin" value={fmtPercent(latest.gross_margin)} />
            <StatCard label="Operating Margin" value={fmtPercent(latest.operating_margin)} />
            <StatCard label="Net Margin" value={fmtPercent(latest.net_margin)} />
            <StatCard label="EBITDA Margin" value={fmtPercent(latest.ebitda_margin)} />
            <StatCard label="ROE" value={fmtPercent(latest.roe)} />
            <StatCard label="ROIC" value={fmtPercent(latest.roic)} />
            <StatCard label="FCF Margin" value={fmtPercent(latest.fcf_margin)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function CompanyOverviewPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();
  return <Overview key={ticker} ticker={ticker} />;
}
