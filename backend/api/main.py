"""
EquityLens API.

Every route is a thin adapter: fetch/derive data via the engines in
backend/{providers,financial_engine,valuation,portfolio,ai,reports}, never
compute finance directly in a route handler. This is also where basic
input validation and rate limiting for the expensive AI endpoint live.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.ai.assistant import AIUnavailableError, ResearchAssistant
from backend.ai.context import AIContext
from backend.database.models import Company, DataSource, ResearchReport
from backend.database.session import get_session, init_db
from backend.financial_engine.ratios import YearFinancials, compute_ratio_series
from backend.portfolio import analytics as portfolio_analytics
from backend.providers.base import ProviderUnavailableError
from backend.providers.live_provider import get_provider
from backend.providers.mock_provider import MockProvider
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
init_db()  # idempotent (CREATE TABLE IF NOT EXISTS); needed for research_reports persistence below

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = get_provider()  # resolved once at startup: live if configured, else demo
_fallback_provider = MockProvider()  # used per-request if a live call fails after startup
logger = logging.getLogger("equitylens.api")


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

def _with_live_fallback(ticker: str, live_call, fallback_call):
    """Try `live_call()` first. If the configured provider is live and the
    call raises ProviderUnavailableError (bad key, network error, rate
    limit), retries via `fallback_call()` against demo data for this one
    request -- logged, and reflected in the returned data_mode, never
    silently relabeled as live. ValueError (e.g. an unknown ticker) is
    never treated as an availability failure and always surfaces as a 404.
    Returns (result, data_mode)."""
    try:
        return live_call(), provider.name
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderUnavailableError as exc:
        if provider.name != "live_api":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        logger.warning("Live provider unavailable for %s (%s); using demo data for this request.", ticker, exc)
        try:
            return fallback_call(), _fallback_provider.name
        except ValueError as exc2:
            raise HTTPException(status_code=404, detail=str(exc2)) from exc2


def _load_years(ticker: str, years: int = 5) -> tuple[list[YearFinancials], str]:
    def load(p) -> list[YearFinancials]:
        inc = sorted(p.get_income_statements(ticker, years), key=lambda s: s.fiscal_year)
        bal = {s.fiscal_year: s.data for s in p.get_balance_sheets(ticker, years)}
        cf = {s.fiscal_year: s.data for s in p.get_cash_flow_statements(ticker, years)}
        return [
            YearFinancials(fiscal_year=s.fiscal_year, income=s.data, balance=bal.get(s.fiscal_year, {}), cash_flow=cf.get(s.fiscal_year, {}))
            for s in inc
        ]

    return _with_live_fallback(ticker, lambda: load(provider), lambda: load(_fallback_provider))


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
    year_objs, data_mode = _load_years(ticker, years)
    # reuse whichever provider _load_years actually used, so the company
    # profile in the same response is never live while the financials it's
    # paired with silently came from the demo fallback (or vice versa)
    active = provider if data_mode == provider.name else _fallback_provider
    ratios = compute_ratio_series(year_objs)
    profile = active.get_company_profile(ticker)
    company = {"ticker": profile.ticker, "name": profile.name, "sector": profile.sector, "industry": profile.industry}
    return year_objs, ratios, company, data_mode


def _get_or_create_company_row(session, company: dict, data_mode: str) -> Company:
    """Research report/AI-answer persistence needs a companies.id foreign
    key, but the API itself never writes to the companies table on the
    read path (it reads live from the provider each request) -- so a row
    may not exist yet for a ticker the caller hasn't seeded. Create one
    lazily from the same profile data already fetched for this request,
    mirroring database/seed.py's fields."""
    ticker = company["ticker"].upper()
    existing = session.query(Company).filter_by(ticker=ticker).one_or_none()
    if existing:
        return existing
    row = Company(
        ticker=ticker,
        name=company.get("name") or ticker,
        sector=company.get("sector"),
        industry=company.get("industry"),
        source=DataSource.LIVE_API if data_mode == "live_api" else DataSource.DEMO,
    )
    session.add(row)
    session.flush()  # assigns row.id without waiting for the outer commit
    return row


def _persist_report(
    company: dict,
    data_mode: str,
    title: str,
    sections: dict,
    *,
    ai_assisted: bool = False,
    generated_by: str = "equitylens-report-engine",
) -> int | None:
    """Best-effort save to research_reports. A database hiccup must never
    turn an already-computed, successful report/answer into an error for
    the caller -- log and return None (caller surfaces id: null) instead
    of raising."""
    try:
        with get_session() as session:
            company_row = _get_or_create_company_row(session, company, data_mode)
            row = ResearchReport(
                company_id=company_row.id,
                title=title,
                sections=sections,
                ai_assisted=ai_assisted,
                generated_by=generated_by,
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception:
        logger.exception("Failed to persist research report for %s", company.get("ticker"))
        return None


# ---------------------------------------------------------------------------
# A. Company search / profile
# ---------------------------------------------------------------------------

@app.get("/api/companies")
def list_companies():
    try:
        return {"tickers": provider.list_supported_tickers(), "data_mode": provider.name}
    except NotImplementedError:
        # LiveProvider deliberately doesn't enumerate every ticker (see its
        # docstring) -- surface that plainly instead of a bare 500, and
        # point callers at exact-ticker search, which does work.
        return {
            "tickers": [],
            "data_mode": provider.name,
            "note": "The live provider does not support listing all tickers. Search by exact ticker, e.g. GET /api/companies/AAPL.",
        }


@app.get("/api/companies/{ticker}")
def get_company(ticker: str):
    def load(p):
        return p.get_company_profile(ticker), p.get_market_quote(ticker)

    (profile, quote), _data_mode = _with_live_fallback(ticker, lambda: load(provider), lambda: load(_fallback_provider))

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
    year_objs, data_mode = _load_years(ticker, years)
    return {
        "ticker": ticker.upper(),
        "data_mode": data_mode,
        "years": [
            {"fiscal_year": y.fiscal_year, "income_statement": y.income, "balance_sheet": y.balance, "cash_flow": y.cash_flow}
            for y in year_objs
        ],
    }


@app.get("/api/companies/{ticker}/ratios")
def get_ratios(ticker: str, years: int = 5):
    year_objs, data_mode = _load_years(ticker, years)
    ratios = compute_ratio_series(year_objs)
    return {"ticker": ticker.upper(), "data_mode": data_mode, "ratios_by_year": ratios}


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
    year_objs, data_mode = _load_years(ticker, 1)
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
        "data_mode": data_mode,
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
    year_objs, data_mode = _load_years(ticker, 1)
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
    return {"ticker": ticker.upper(), "data_mode": data_mode, "scenarios": scenario_output}


# E. Sensitivity table
@app.post("/api/companies/{ticker}/dcf/sensitivity")
def run_sensitivity(ticker: str, req: DCFRequest, wacc_min: float = 0.06, wacc_max: float = 0.14, growth_min: float = 0.0, growth_max: float = 0.04):
    year_objs, data_mode = _load_years(ticker, 1)
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
    return {"ticker": ticker.upper(), "data_mode": data_mode, **table}


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
    year_objs, data_mode = _load_years(ticker, 1)
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
        "data_mode": data_mode,
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
    # Annualization/Sharpe/volatility assume this many price observations
    # per year. Default (252) matches daily trading days -- callers with
    # weekly/monthly price series must override this or the annualized
    # figures will be wildly wrong. Echoed back in the response so the UI
    # can always show what assumption was actually used.
    periods_per_year: int = Field(252, ge=1, le=366)


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
        ar = portfolio_analytics.annualized_return(portfolio_prices, periods_per_year=req.periods_per_year)
        port_returns = portfolio_analytics.prices_to_returns(portfolio_prices)
        vol = portfolio_analytics.volatility(port_returns, periods_per_year=req.periods_per_year)
        sharpe = portfolio_analytics.sharpe_ratio(
            port_returns, req.risk_free_rate_annual, periods_per_year=req.periods_per_year
        )
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
        # Echoed back so the UI can always display the assumption actually
        # used, rather than silently guessing at the caller's data frequency.
        "periods_per_year": req.periods_per_year,
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

    year_objs, ratios, company, data_mode = _company_and_ratios(ticker, 5)

    ctx = AIContext(
        company=company,
        financials={y.fiscal_year: {"income_statement": y.income, "balance_sheet": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios=ratios,
        data_mode=data_mode,
    )

    assistant = ResearchAssistant()
    try:
        # sanitize: strip any prompt-injection-style control tokens from user input
        clean_question = req.question.replace("\x00", "").strip()
        answer = assistant.ask(ctx, clean_question)
    except AIUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    saved_id = _persist_report(
        company,
        data_mode,
        title=f"AI Q&A: {clean_question[:120]}",
        sections={"question": clean_question, "answer": answer},
        ai_assisted=True,
        generated_by="ai-research-assistant",
    )

    return {
        "ticker": ticker.upper(),
        "question": req.question,
        "answer": answer,
        "data_mode": data_mode,
        "id": saved_id,
    }


# ---------------------------------------------------------------------------
# I. Research report
# ---------------------------------------------------------------------------

@app.get("/api/companies/{ticker}/report")
def generate_report(ticker: str):
    """Quick report from financials/ratios alone — no valuation section
    filled in. Use POST /report to include DCF/comparables/scenario/AI
    results the caller already computed (see that handler's docstring).
    Not persisted: this fires automatically on every Report-tab page load,
    so saving it would flood research_reports with duplicates the user
    never asked to keep -- only the explicit POST (regenerate) is saved."""
    year_objs, ratios, company, data_mode = _company_and_ratios(ticker, 5)

    inputs = ReportInputs(
        company=company,
        financials_by_year={y.fiscal_year: {"income": y.income, "balance": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios_by_year=ratios,
        data_mode=data_mode,
    )
    report = build_report(inputs)
    report["id"] = None
    return report


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
    year_objs, ratios, company, data_mode = _company_and_ratios(ticker, 5)

    inputs = ReportInputs(
        company=company,
        financials_by_year={y.fiscal_year: {"income": y.income, "balance": y.balance, "cash_flow": y.cash_flow} for y in year_objs},
        ratios_by_year=ratios,
        dcf_result=req.dcf_result,
        dcf_assumptions=req.dcf_assumptions,
        comparables=req.comparables,
        scenarios=req.scenarios,
        data_mode=data_mode,
        ai_narrative=req.ai_narrative,
    )
    report = build_report(inputs)
    report["id"] = _persist_report(
        company,
        data_mode,
        title=report["title"],
        sections=report["sections"],
        ai_assisted=bool(req.ai_narrative),
    )
    return report


@app.get("/api/companies/{ticker}/reports")
def list_saved_reports(ticker: str, limit: int = 20):
    """Previously generated (POST /report) reports and AI Q&A answers for
    this ticker, most recent first -- see research_reports in the schema
    (docs/ARCHITECTURE.md). Unknown/never-saved-to ticker returns an empty
    list rather than 404, since "no saved reports yet" isn't an error."""
    with get_session() as session:
        company_row = session.query(Company).filter_by(ticker=ticker.upper()).one_or_none()
        rows = (
            session.query(ResearchReport)
            .filter_by(company_id=company_row.id)
            .order_by(ResearchReport.created_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
            if company_row
            else []
        )
        return {
            "ticker": ticker.upper(),
            "reports": [
                {
                    "id": r.id,
                    "title": r.title,
                    "generated_by": r.generated_by,
                    "ai_assisted": r.ai_assisted,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }


@app.get("/api/companies/{ticker}/reports/{report_id}")
def get_saved_report(ticker: str, report_id: int):
    with get_session() as session:
        company_row = session.query(Company).filter_by(ticker=ticker.upper()).one_or_none()
        row = (
            session.query(ResearchReport).filter_by(id=report_id, company_id=company_row.id).one_or_none()
            if company_row
            else None
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"No saved report {report_id} for {ticker.upper()}.")
        return {
            "id": row.id,
            "ticker": ticker.upper(),
            "title": row.title,
            "sections": row.sections,
            "generated_by": row.generated_by,
            "ai_assisted": row.ai_assisted,
            "created_at": row.created_at.isoformat(),
        }


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": provider.name}
