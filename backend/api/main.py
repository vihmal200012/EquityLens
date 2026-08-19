"""
EquityLens API.

Every route is a thin adapter: fetch/derive data via the engines in
backend/{providers,financial_engine,valuation,portfolio,ai,reports}, never
compute finance directly in a route handler. This is also where basic
input validation and rate limiting for the expensive AI endpoint live.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.ai.assistant import AIUnavailableError, ResearchAssistant
from backend.ai.context import AIContext
from backend.financial_engine.ratios import YearFinancials, compute_ratio_series
from backend.portfolio import analytics as portfolio_analytics
from backend.providers.base import ProviderUnavailableError
from backend.providers.live_provider import get_provider
from backend.reports.generator import ReportInputs, build_report
from backend.valuation.comparables import PeerFinancials, run_comparable_valuation
from backend.valuation.dcf import (
    DCFAssumptions,
    InvalidAssumptionsError,
    build_default_scenarios,
    run_dcf,
    run_scenarios,
    sensitivity_table,
)

app = FastAPI(title="EquityLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = get_provider()  # resolved once at startup: live if configured, else demo


# ---------------------------------------------------------------------------
# Minimal in-memory rate limiter for the expensive AI endpoint
# ---------------------------------------------------------------------------

_AI_RATE_LIMIT = 10          # requests
_AI_RATE_WINDOW_SEC = 60     # per this many seconds
_ai_call_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_id: str) -> None:
    now = time.time()
    window_start = now - _AI_RATE_WINDOW_SEC
    calls = [t for t in _ai_call_log[client_id] if t >= window_start]
    if len(calls) >= _AI_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="AI rate limit exceeded. Try again shortly.")
    calls.append(now)
    _ai_call_log[client_id] = calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_years(ticker: str, years: int = 5) -> list[YearFinancials]:
    try:
        inc = sorted(provider.get_income_statements(ticker, years), key=lambda s: s.fiscal_year)
        bal = {s.fiscal_year: s.data for s in provider.get_balance_sheets(ticker, years)}
        cf = {s.fiscal_year: s.data for s in provider.get_cash_flow_statements(ticker, years)}
    except (ValueError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        YearFinancials(fiscal_year=s.fiscal_year, income=s.data, balance=bal.get(s.fiscal_year, {}), cash_flow=cf.get(s.fiscal_year, {}))
        for s in inc
    ]


def _net_debt_and_shares(latest: YearFinancials) -> tuple[float, float]:
    """Shared by every endpoint that bridges enterprise value to a per-share
    price. Raises a clean 422 if shares_outstanding is missing rather than
    letting a bare-None division blow up as an unhandled 500 — this matters
    once a provider (e.g. a live one) doesn't populate every field the demo
    data always has."""
    net_debt = latest.balance.get("total_debt", 0) - latest.balance.get("cash_and_equivalents", 0)
    shares = latest.balance.get("shares_outstanding")
    if not shares:
        raise HTTPException(status_code=422, detail="Missing shares_outstanding for this company.")
    return net_debt, shares


def _company_and_ratios(ticker: str, years: int = 5):
    year_objs = _load_years(ticker, years)
    ratios = compute_ratio_series(year_objs)
    profile = provider.get_company_profile(ticker)
    company = {"ticker": profile.ticker, "name": profile.name, "sector": profile.sector, "industry": profile.industry}
    return year_objs, ratios, company


# ---------------------------------------------------------------------------
# A. Company search / profile
# ---------------------------------------------------------------------------

@app.get("/api/companies")
def list_companies():
    return {"tickers": provider.list_supported_tickers(), "data_mode": provider.name}


@app.get("/api/companies/{ticker}")
def get_company(ticker: str):
    try:
        profile = provider.get_company_profile(ticker)
        quote = provider.get_market_quote(ticker)
    except (ValueError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "ticker": profile.ticker,
        "name": profile.name,
        "sector": profile.sector,
        "industry": profile.industry,
        "description": profile.description,
        "shares_outstanding": profile.shares_outstanding,
        "price": quote.price,
        "market_cap": quote.market_cap,
        "enterprise_value": quote.enterprise_value,
        "data_mode": profile.source,
    }


# ---------------------------------------------------------------------------
# B. Financial statements + ratios
# ---------------------------------------------------------------------------

@app.get("/api/companies/{ticker}/financials")
def get_financials(ticker: str, years: int = 5):
    year_objs = _load_years(ticker, years)
    return {
        "ticker": ticker.upper(),
        "data_mode": provider.name,
        "years": [
            {"fiscal_year": y.fiscal_year, "income_statement": y.income, "balance_sheet": y.balance, "cash_flow": y.cash_flow}
            for y in year_objs
        ],
    }


@app.get("/api/companies/{ticker}/ratios")
def get_ratios(ticker: str, years: int = 5):
    year_objs = _load_years(ticker, years)
    ratios = compute_ratio_series(year_objs)
    return {"ticker": ticker.upper(), "data_mode": provider.name, "ratios_by_year": ratios}


# ---------------------------------------------------------------------------
# C. DCF valuation
# ---------------------------------------------------------------------------

class DCFRequest(BaseModel):
    revenue_growth_rates: list[float] = Field(..., min_length=1, max_length=10)
    ebit_margin: float = Field(..., ge=-1, le=1)
    tax_rate: float = Field(..., ge=0, le=1)
    da_pct_revenue: float = Field(..., ge=0, le=1)
    capex_pct_revenue: float = Field(..., ge=0, le=1)
    nwc_pct_revenue_change: float = Field(..., ge=-1, le=1)
    wacc: float = Field(..., gt=0, le=1)
    terminal_growth: float = Field(..., ge=-0.1, le=0.5)

    @field_validator("revenue_growth_rates")
    @classmethod
    def growth_rates_reasonable(cls, v):
        for g in v:
            if g < -0.9 or g > 5:
                raise ValueError("revenue_growth_rates must be between -90% and 500%.")
        return v


@app.post("/api/companies/{ticker}/dcf")
def run_dcf_valuation(ticker: str, req: DCFRequest):
    year_objs = _load_years(ticker, 1)
    latest = year_objs[-1]
    net_debt, shares = _net_debt_and_shares(latest)

    assumptions = DCFAssumptions(
        base_revenue=latest.income["revenue"],
        revenue_growth_rates=req.revenue_growth_rates,
        ebit_margin=req.ebit_margin,
        tax_rate=req.tax_rate,
        da_pct_revenue=req.da_pct_revenue,
        capex_pct_revenue=req.capex_pct_revenue,
        nwc_pct_revenue_change=req.nwc_pct_revenue_change,
        wacc=req.wacc,
        terminal_growth=req.terminal_growth,
        net_debt=net_debt,
        shares_outstanding=shares,
    )
    try:
        result = run_dcf(assumptions)
    except InvalidAssumptionsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "ticker": ticker.upper(),
        "data_mode": provider.name,
        "implied_share_price": round(result.implied_share_price, 2),
        "enterprise_value": round(result.enterprise_value, 1),
        "equity_value": round(result.equity_value, 1),
        "sum_pv_fcf": round(result.sum_pv_fcf, 1),
        "terminal_value": round(result.terminal_value, 1),
        "pv_terminal_value": round(result.pv_terminal_value, 1),
        "forecast": [f.__dict__ for f in result.forecast],
    }


# D. Scenario analysis
@app.post("/api/companies/{ticker}/dcf/scenarios")
def run_dcf_scenarios(ticker: str, req: DCFRequest):
    year_objs = _load_years(ticker, 1)
    latest = year_objs[-1]
    net_debt, shares = _net_debt_and_shares(latest)

    base = DCFAssumptions(
        base_revenue=latest.income["revenue"],
        revenue_growth_rates=req.revenue_growth_rates,
        ebit_margin=req.ebit_margin,
        tax_rate=req.tax_rate,
        da_pct_revenue=req.da_pct_revenue,
        capex_pct_revenue=req.capex_pct_revenue,
        nwc_pct_revenue_change=req.nwc_pct_revenue_change,
        wacc=req.wacc,
        terminal_growth=req.terminal_growth,
        net_debt=net_debt,
        shares_outstanding=shares,
    )
    try:
        scenarios = build_default_scenarios(base)
        results = run_scenarios(scenarios)
    except InvalidAssumptionsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scenario_output = {
        name: {"implied_share_price": round(r.implied_share_price, 2), "enterprise_value": round(r.enterprise_value, 1)}
        for name, r in results.items()
    }
    return {"ticker": ticker.upper(), "data_mode": provider.name, "scenarios": scenario_output}


# E. Sensitivity table
@app.post("/api/companies/{ticker}/dcf/sensitivity")
def run_sensitivity(ticker: str, req: DCFRequest, wacc_min: float = 0.06, wacc_max: float = 0.14, growth_min: float = 0.0, growth_max: float = 0.04):
    year_objs = _load_years(ticker, 1)
    latest = year_objs[-1]
    net_debt, shares = _net_debt_and_shares(latest)

    base = DCFAssumptions(
        base_revenue=latest.income["revenue"],
        revenue_growth_rates=req.revenue_growth_rates,
        ebit_margin=req.ebit_margin,
        tax_rate=req.tax_rate,
        da_pct_revenue=req.da_pct_revenue,
        capex_pct_revenue=req.capex_pct_revenue,
        nwc_pct_revenue_change=req.nwc_pct_revenue_change,
        wacc=req.wacc,
        terminal_growth=req.terminal_growth,
        net_debt=net_debt,
        shares_outstanding=shares,
    )
    wacc_steps = [round(wacc_min + i * (wacc_max - wacc_min) / 6, 4) for i in range(7)]
    growth_steps = [round(growth_min + i * (growth_max - growth_min) / 4, 4) for i in range(5)]
    table = sensitivity_table(base, wacc_steps, growth_steps)
    return {"ticker": ticker.upper(), "data_mode": provider.name, **table}


# ---------------------------------------------------------------------------
# F. Comparable company analysis
# ---------------------------------------------------------------------------

class PeerInput(BaseModel):
    ticker: str
    price: float
    shares_outstanding: float
    net_income: float
    ebitda: float
    revenue: float
    total_debt: float
    cash: float
    free_cash_flow: float
    revenue_prior_year: float | None = None


class ComparablesRequest(BaseModel):
    peers: list[PeerInput] = Field(..., min_length=1, max_length=15)


@app.post("/api/companies/{ticker}/comparables")
def run_comparables(ticker: str, req: ComparablesRequest):
    year_objs = _load_years(ticker, 1)
    latest = year_objs[-1]
    net_debt, shares = _net_debt_and_shares(latest)

    peers = [PeerFinancials(**p.model_dump()) for p in req.peers]
    try:
        result = run_comparable_valuation(
            peers,
            subject_net_income=latest.income.get("net_income"),
            subject_ebitda=latest.income.get("ebitda"),
            subject_revenue=latest.income.get("revenue"),
            subject_net_debt=net_debt,
            subject_shares_outstanding=shares,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "ticker": ticker.upper(),
        "data_mode": provider.name,
        "median_pe": result.median_pe,
        "mean_pe": result.mean_pe,
        "median_ev_ebitda": result.median_ev_ebitda,
        "mean_ev_ebitda": result.mean_ev_ebitda,
        "median_ev_revenue": result.median_ev_revenue,
        "mean_ev_revenue": result.mean_ev_revenue,
        "implied_price_from_pe": result.implied_price_from_pe,
        "implied_price_from_ev_ebitda": result.implied_price_from_ev_ebitda,
        "implied_price_from_ev_revenue": result.implied_price_from_ev_revenue,
        "methodology_note": result.methodology_note,
        "peer_multiples": [m.__dict__ for m in result.peer_multiples],
    }


# ---------------------------------------------------------------------------
# G. Portfolio analysis
# ---------------------------------------------------------------------------

class PortfolioRequest(BaseModel):
    prices_by_ticker: dict[str, list[float]] = Field(..., min_length=1)
    weights: dict[str, float] | None = None
    benchmark_prices: list[float] | None = None
    risk_free_rate_annual: float = 0.0


@app.post("/api/portfolio/analyze")
def analyze_portfolio(req: PortfolioRequest):
    lengths = {len(v) for v in req.prices_by_ticker.values()}
    if len(lengths) != 1:
        raise HTTPException(status_code=422, detail="All tickers must have the same number of price observations.")

    returns_by_ticker = {t: portfolio_analytics.prices_to_returns(p) for t, p in req.prices_by_ticker.items()}

    weights = req.weights or {t: 1 / len(req.prices_by_ticker) for t in req.prices_by_ticker}
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise HTTPException(status_code=422, detail="weights must sum to 1.0")

    # weighted portfolio price series
    n_periods = len(next(iter(req.prices_by_ticker.values())))
    portfolio_prices = []
    for i in range(n_periods):
        portfolio_prices.append(sum(weights[t] * req.prices_by_ticker[t][i] / req.prices_by_ticker[t][0] for t in weights))

    try:
        tr = portfolio_analytics.total_return(portfolio_prices)
        ar = portfolio_analytics.annualized_return(portfolio_prices)
        port_returns = portfolio_analytics.prices_to_returns(portfolio_prices)
        vol = portfolio_analytics.volatility(port_returns)
        sharpe = portfolio_analytics.sharpe_ratio(port_returns, req.risk_free_rate_annual)
        dd = portfolio_analytics.max_drawdown(portfolio_prices)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = {
        "total_return": tr,
        "annualized_return": ar,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": dd.max_drawdown,
        "weights": weights,
        "portfolio_value_series": portfolio_prices,
        "drawdown_series": dd.drawdown_series,
    }

    if req.benchmark_prices:
        bench_returns = portfolio_analytics.prices_to_returns(req.benchmark_prices)
        if len(bench_returns) == len(port_returns):
            result["beta"] = portfolio_analytics.beta(port_returns, bench_returns)

    if len(returns_by_ticker) > 1:
        result["correlation_matrix"] = portfolio_analytics.correlation_matrix(returns_by_ticker)

    return result


# ---------------------------------------------------------------------------
# H. AI research assistant
# ---------------------------------------------------------------------------

class AIQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.post("/api/companies/{ticker}/ai/ask")
def ask_ai(ticker: str, req: AIQuestionRequest, request: Request):
    client_id = request.client.host if request.client else "unknown"
    _check_rate_limit(client_id)

    year_objs, ratios, company = _company_and_ratios(ticker, 5)

    ctx = AIContext(
        company=company,
        financials={y.fiscal_year: {"income_statement": y.income, "balance_sheet": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios=ratios,
        data_mode=provider.name,
    )

    assistant = ResearchAssistant()
    try:
        # sanitize: strip any prompt-injection-style control tokens from user input
        clean_question = req.question.replace("\x00", "").strip()
        answer = assistant.ask(ctx, clean_question)
    except AIUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"ticker": ticker.upper(), "question": req.question, "answer": answer, "data_mode": provider.name}


# ---------------------------------------------------------------------------
# I. Research report
# ---------------------------------------------------------------------------

@app.get("/api/companies/{ticker}/report")
def generate_report(ticker: str):
    """Quick report from financials/ratios alone — no valuation section
    filled in. Use POST /report to include DCF/comparables/scenario/AI
    results the caller already computed (see that handler's docstring)."""
    year_objs, ratios, company = _company_and_ratios(ticker, 5)

    inputs = ReportInputs(
        company=company,
        financials_by_year={y.fiscal_year: {"income": y.income, "balance": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios_by_year=ratios,
        data_mode=provider.name,
    )
    return build_report(inputs)


class ReportRequest(BaseModel):
    """Everything here is optional: pass whatever the caller already
    computed via /dcf, /dcf/scenarios, /comparables, and/or /ai/ask so the
    report reflects the same numbers shown elsewhere in the app, instead of
    the engine silently recomputing (or worse, never including) them."""

    dcf_result: dict | None = None
    dcf_assumptions: dict | None = None
    comparables: dict | None = None
    scenarios: dict | None = None
    ai_narrative: dict | None = None


@app.post("/api/companies/{ticker}/report")
def generate_full_report(ticker: str, req: ReportRequest):
    year_objs, ratios, company = _company_and_ratios(ticker, 5)

    inputs = ReportInputs(
        company=company,
        financials_by_year={y.fiscal_year: {"income": y.income, "balance": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios_by_year=ratios,
        dcf_result=req.dcf_result,
        dcf_assumptions=req.dcf_assumptions,
        comparables=req.comparables,
        scenarios=req.scenarios,
        data_mode=provider.name,
        ai_narrative=req.ai_narrative,
    )
    return build_report(inputs)


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": provider.name}
