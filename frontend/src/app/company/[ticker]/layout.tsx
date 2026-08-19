"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError, CompanyProfile } from "@/lib/api";
import DataModeBadge from "@/components/DataModeBadge";
import CompanyTabs from "@/components/CompanyTabs";
import { ErrorBanner, LoadingState } from "@/components/StatusStates";
import { fmtCurrency, fmtMoneyFromMillions } from "@/lib/format";

function CompanyHeader({ ticker }: { ticker: string }) {
  const [company, setCompany] = useState<CompanyProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getCompany(ticker)
      .then(setCompany)
      .catch((e: ApiError) => setError(e.message));
  }, [ticker]);

  if (error) return <ErrorBanner message={error} />;
  if (!company) return <LoadingState label={`Loading ${ticker}…`} />;

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {company.name} <span className="text-black/40 dark:text-white/40">({company.ticker})</span>
          </h1>
          <DataModeBadge mode={company.data_mode} />
        </div>
        <p className="mt-1 text-sm text-black/60 dark:text-white/60">
          {company.sector} · {company.industry}
        </p>
      </div>
      <div className="flex gap-6 text-right">
        <div>
          <div className="text-xs uppercase tracking-wide text-black/50 dark:text-white/50">Price</div>
          <div className="text-lg font-semibold tabular-nums">{fmtCurrency(company.price)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-black/50 dark:text-white/50">Market Cap</div>
          <div className="text-lg font-semibold tabular-nums">{fmtMoneyFromMillions(company.market_cap)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-black/50 dark:text-white/50">Enterprise Value</div>
          <div className="text-lg font-semibold tabular-nums">{fmtMoneyFromMillions(company.enterprise_value)}</div>
        </div>
      </div>
    </div>
  );
}

export default function CompanyLayout({ children }: LayoutProps<"/company/[ticker]">) {
  const params = useParams<{ ticker: string }>();
  const ticker = (params.ticker || "").toUpperCase();

  return (
    <div className="space-y-6">
      <CompanyHeader key={ticker} ticker={ticker} />
      <CompanyTabs ticker={ticker} />
      <div>{children}</div>
    </div>
  );
}
