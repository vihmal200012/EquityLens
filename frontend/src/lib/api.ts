const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError(0, `Could not reach the EquityLens API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : detail;
    } catch {
      // ignore non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DataMode = "demo" | "live_api" | string;

export interface CompanyListResponse {
  tickers: string[];
  data_mode: DataMode;
  note?: string;
}

export interface CompanyProfile {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  description: string;
  shares_outstanding: number;
  price: number;
  market_cap: number;
  enterprise_value: number;
  data_mode: DataMode;
}

export interface YearFinancialsResponse {
  fiscal_year: number;
  income_statement: Record<string, number>;
  balance_sheet: Record<string, number>;
  cash_flow: Record<string, number>;
}

export interface FinancialsResponse {
  ticker: string;
  data_mode: DataMode;
  years: YearFinancialsResponse[];
}

export interface RatiosResponse {
  ticker: string;
  data_mode: DataMode;
  ratios_by_year: Record<string, Record<string, number | null>>;
}

export interface DCFAssumptionsInput {
  revenue_growth_rates: number[];
  ebit_margin: number;
  tax_rate: number;
  da_pct_revenue: number;
  capex_pct_revenue: number;
  nwc_pct_revenue_change: number;
  wacc: number;
  terminal_growth: number;
}

export interface DCFForecastYear {
  year_index: number;
  revenue: number;
  ebit: number;
  nopat: number;
  da: number;
  capex: number;
  nwc_change: number;
  fcf: number;
  discount_factor: number;
  pv_fcf: number;
}

export interface DCFResponse {
  ticker: string;
  data_mode: DataMode;
  implied_share_price: number;
  enterprise_value: number;
  equity_value: number;
  sum_pv_fcf: number;
  terminal_value: number;
  pv_terminal_value: number;
  forecast: DCFForecastYear[];
}

export interface DCFScenariosResponse {
  ticker: string;
  data_mode: DataMode;
  scenarios: Record<string, { implied_share_price: number; enterprise_value: number }>;
}

export interface DCFSensitivityResponse {
  ticker: string;
  data_mode: DataMode;
  wacc_values: number[];
  growth_values: number[];
  prices: (number | null)[][];
}

export interface PeerInput {
  ticker: string;
  price: number;
  shares_outstanding: number;
  net_income: number;
  ebitda: number;
  revenue: number;
  total_debt: number;
  cash: number;
  free_cash_flow: number;
  revenue_prior_year?: number | null;
}

export interface PeerMultiple {
  ticker: string;
  pe: number | null;
  ev_ebitda: number | null;
  ev_revenue: number | null;
  price_sales: number | null;
  fcf_yield: number | null;
  revenue_growth: number | null;
  ebitda_margin: number | null;
}

export interface ComparablesResponse {
  ticker: string;
  data_mode: DataMode;
  median_pe: number | null;
  mean_pe: number | null;
  median_ev_ebitda: number | null;
  mean_ev_ebitda: number | null;
  median_ev_revenue: number | null;
  mean_ev_revenue: number | null;
  implied_price_from_pe: number | null;
  implied_price_from_ev_ebitda: number | null;
  implied_price_from_ev_revenue: number | null;
  methodology_note: string;
  peer_multiples: PeerMultiple[];
}

export interface PortfolioRequestInput {
  prices_by_ticker: Record<string, number[]>;
  weights?: Record<string, number> | null;
  benchmark_prices?: number[] | null;
  risk_free_rate_annual?: number;
  // Price observations per year, for annualizing return/volatility/Sharpe.
  // Defaults to 252 (daily trading days) on the backend if omitted.
  periods_per_year?: number;
}

// Matches backend/portfolio/analytics.py::correlation_matrix — a
// JSON-friendly matrix keyed by parallel ticker order, not a nested
// per-ticker dict.
export interface CorrelationMatrix {
  tickers: string[];
  matrix: number[][];
}

export interface PortfolioResponse {
  total_return: number;
  annualized_return: number;
  volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  weights: Record<string, number>;
  portfolio_value_series: number[];
  drawdown_series: number[];
  beta?: number;
  correlation_matrix?: CorrelationMatrix;
  // The annualization frequency actually used, echoed back by the backend
  // (see PortfolioRequestInput.periods_per_year) so the UI can always show
  // the assumption behind the annualized figures.
  periods_per_year: number;
}

export interface AIAskResponse {
  ticker: string;
  question: string;
  answer: string;
  data_mode: DataMode;
}

export interface ReportResponse {
  title: string;
  generated_at: string;
  data_mode: DataMode;
  sections: Record<string, string>;
}

export interface HealthResponse {
  status: string;
  provider: string;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export const api = {
  health: () => get<HealthResponse>("/api/health"),
  listCompanies: () => get<CompanyListResponse>("/api/companies"),
  getCompany: (ticker: string) => get<CompanyProfile>(`/api/companies/${encodeURIComponent(ticker)}`),
  getFinancials: (ticker: string, years = 5) =>
    get<FinancialsResponse>(`/api/companies/${encodeURIComponent(ticker)}/financials?years=${years}`),
  getRatios: (ticker: string, years = 5) =>
    get<RatiosResponse>(`/api/companies/${encodeURIComponent(ticker)}/ratios?years=${years}`),
  runDCF: (ticker: string, req: DCFAssumptionsInput) =>
    post<DCFResponse>(`/api/companies/${encodeURIComponent(ticker)}/dcf`, req),
  runDCFScenarios: (ticker: string, req: DCFAssumptionsInput) =>
    post<DCFScenariosResponse>(`/api/companies/${encodeURIComponent(ticker)}/dcf/scenarios`, req),
  runSensitivity: (
    ticker: string,
    req: DCFAssumptionsInput,
    bounds?: { wacc_min?: number; wacc_max?: number; growth_min?: number; growth_max?: number }
  ) => {
    const params = new URLSearchParams();
    if (bounds?.wacc_min !== undefined) params.set("wacc_min", String(bounds.wacc_min));
    if (bounds?.wacc_max !== undefined) params.set("wacc_max", String(bounds.wacc_max));
    if (bounds?.growth_min !== undefined) params.set("growth_min", String(bounds.growth_min));
    if (bounds?.growth_max !== undefined) params.set("growth_max", String(bounds.growth_max));
    const qs = params.toString();
    return post<DCFSensitivityResponse>(
      `/api/companies/${encodeURIComponent(ticker)}/dcf/sensitivity${qs ? `?${qs}` : ""}`,
      req
    );
  },
  runComparables: (ticker: string, peers: PeerInput[]) =>
    post<ComparablesResponse>(`/api/companies/${encodeURIComponent(ticker)}/comparables`, { peers }),
  analyzePortfolio: (req: PortfolioRequestInput) => post<PortfolioResponse>("/api/portfolio/analyze", req),
  askAI: (ticker: string, question: string) =>
    post<AIAskResponse>(`/api/companies/${encodeURIComponent(ticker)}/ai/ask`, { question }),
  getQuickReport: (ticker: string) => get<ReportResponse>(`/api/companies/${encodeURIComponent(ticker)}/report`),
  getFullReport: (
    ticker: string,
    req: {
      dcf_result?: unknown;
      dcf_assumptions?: unknown;
      comparables?: unknown;
      scenarios?: unknown;
      ai_narrative?: unknown;
    }
  ) => post<ReportResponse>(`/api/companies/${encodeURIComponent(ticker)}/report`, req),
};
