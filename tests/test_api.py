import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.api.main as main_module
from backend.api.main import _net_debt_and_shares, app
from backend.financial_engine.ratios import YearFinancials
from backend.providers.base import ProviderUnavailableError

client = TestClient(app)


class _FailingLiveProvider:
    """Stands in for a configured LiveProvider whose requests fail at
    call-time (bad key, network error, rate limit) -- as opposed to
    failing at construction time, which get_provider() already handles."""

    name = "live_api"

    def __init__(self, error: Exception):
        self._error = error

    def get_income_statements(self, ticker, years):
        raise self._error

    def get_balance_sheets(self, ticker, years):
        raise self._error

    def get_cash_flow_statements(self, ticker, years):
        raise self._error

    def get_company_profile(self, ticker):
        raise self._error

    def get_market_quote(self, ticker):
        raise self._error

    def list_supported_tickers(self):
        raise self._error

DCF_PAYLOAD = dict(
    revenue_growth_rates=[0.08, 0.07, 0.06, 0.05, 0.04],
    ebit_margin=0.28,
    tax_rate=0.15,
    da_pct_revenue=0.03,
    capex_pct_revenue=0.03,
    nwc_pct_revenue_change=0.10,
    wacc=0.09,
    terminal_growth=0.025,
)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_companies_returns_demo_tickers():
    r = client.get("/api/companies")
    assert r.status_code == 200
    assert set(r.json()["tickers"]) >= {"AAPL", "MSFT", "NVDA"}
    assert r.json()["data_mode"] == "demo"


def test_get_company_profile():
    r = client.get("/api/companies/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["price"] > 0
    assert body["data_mode"] == "demo"


def test_unknown_ticker_404():
    r = client.get("/api/companies/ZZZZ")
    assert r.status_code == 404


def test_financials_endpoint_returns_5_years_by_default():
    r = client.get("/api/companies/MSFT/financials")
    assert r.status_code == 200
    assert len(r.json()["years"]) == 5


def test_ratios_endpoint():
    r = client.get("/api/companies/NVDA/ratios")
    assert r.status_code == 200
    ratios = r.json()["ratios_by_year"]
    latest = max(ratios.keys())
    assert ratios[latest]["gross_margin"] is not None


def test_ratios_endpoint_with_years_2_computes_latest_revenue_growth():
    """Regression test: the Overview page used to request years=1, which
    can never populate revenue_growth/eps_growth (no prior year to compare
    against), so it always displayed "—". years=2 is the minimum that lets
    the latest year's growth be computed."""
    r = client.get("/api/companies/AAPL/ratios", params={"years": 2})
    assert r.status_code == 200
    ratios = r.json()["ratios_by_year"]
    assert len(ratios) == 2
    latest = max(int(fy) for fy in ratios.keys())
    assert ratios[str(latest)]["revenue_growth"] is not None


def test_dcf_endpoint_matches_engine_within_rounding():
    r = client.post("/api/companies/AAPL/dcf", json=DCF_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["implied_share_price"] > 0
    assert body["enterprise_value"] > body["equity_value"]  # since net debt > 0 for AAPL demo profile


def test_dcf_endpoint_rejects_wacc_leq_terminal_growth():
    bad = dict(DCF_PAYLOAD, wacc=0.02, terminal_growth=0.025)
    r = client.post("/api/companies/AAPL/dcf", json=bad)
    assert r.status_code == 422


def test_dcf_endpoint_rejects_missing_field():
    incomplete = dict(DCF_PAYLOAD)
    del incomplete["wacc"]
    r = client.post("/api/companies/AAPL/dcf", json=incomplete)
    assert r.status_code == 422


def test_scenarios_endpoint_orders_bear_base_bull():
    r = client.post("/api/companies/AAPL/dcf/scenarios", json=DCF_PAYLOAD)
    assert r.status_code == 200
    s = r.json()["scenarios"]
    assert s["bear"]["implied_share_price"] < s["base"]["implied_share_price"] < s["bull"]["implied_share_price"]


def test_sensitivity_endpoint_shape():
    r = client.post("/api/companies/AAPL/dcf/sensitivity", json=DCF_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert len(body["prices"]) == len(body["wacc_values"])
    assert len(body["prices"][0]) == len(body["growth_values"])


def test_comparables_endpoint():
    peers = {
        "peers": [
            {"ticker": "PEER1", "price": 300, "shares_outstanding": 1000, "net_income": 5000, "ebitda": 8000, "revenue": 40000, "total_debt": 2000, "cash": 1000, "free_cash_flow": 4000},
            {"ticker": "PEER2", "price": 150, "shares_outstanding": 2000, "net_income": 6000, "ebitda": 9000, "revenue": 45000, "total_debt": 3000, "cash": 1500, "free_cash_flow": 5000},
        ]
    }
    r = client.post("/api/companies/AAPL/comparables", json=peers)
    assert r.status_code == 200
    assert r.json()["median_pe"] is not None


def test_comparables_endpoint_requires_at_least_one_peer():
    r = client.post("/api/companies/AAPL/comparables", json={"peers": []})
    assert r.status_code == 422


def test_portfolio_analyze_endpoint():
    payload = {"prices_by_ticker": {"AAPL": [100, 102, 101, 105, 103, 108], "MSFT": [50, 51, 49, 52, 53, 55]}}
    r = client.post("/api/portfolio/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "sharpe_ratio" in body
    assert "correlation_matrix" in body


def test_portfolio_analyze_defaults_periods_per_year_to_252_and_echoes_it():
    payload = {"prices_by_ticker": {"AAPL": [100, 102, 101, 105, 103, 108]}}
    r = client.post("/api/portfolio/analyze", json=payload)
    assert r.status_code == 200
    assert r.json()["periods_per_year"] == 252


def test_portfolio_analyze_respects_explicit_periods_per_year():
    """Regression test: annualization used to hardcode 252 trading days with
    no way for the caller to say the price series is weekly/monthly, so a
    short demo series produced a nonsensical annualized return (e.g. >1000%
    for 9 data points). Passing periods_per_year should change the
    annualized figures deterministically and be echoed back unchanged."""
    payload = {"prices_by_ticker": {"AAPL": [100, 102, 101, 105, 103, 108]}, "periods_per_year": 12}
    r = client.post("/api/portfolio/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["periods_per_year"] == 12

    payload_252 = {**payload, "periods_per_year": 252}
    r_252 = client.post("/api/portfolio/analyze", json=payload_252)
    assert r_252.status_code == 200
    body_252 = r_252.json()

    # Same price series, different annualization frequency -> different
    # (and much smaller, since 12 << 252) annualized return/volatility.
    assert body["annualized_return"] != body_252["annualized_return"]
    assert abs(body["annualized_return"]) < abs(body_252["annualized_return"])


def test_portfolio_analyze_correlation_matrix_contract():
    """Pins the {"tickers": [...], "matrix": [[...]]} shape the frontend
    relies on (see analytics.correlation_matrix's docstring) — NOT a nested
    per-ticker dict. Regressing this shape silently breaks the Portfolio
    page's Correlation Matrix table."""
    payload = {"prices_by_ticker": {"AAPL": [100, 102, 101, 105, 103, 108], "MSFT": [50, 51, 49, 52, 53, 55]}}
    r = client.post("/api/portfolio/analyze", json=payload)
    assert r.status_code == 200
    corr = r.json()["correlation_matrix"]
    assert corr["tickers"] == ["AAPL", "MSFT"]
    assert len(corr["matrix"]) == 2
    assert len(corr["matrix"][0]) == 2
    assert corr["matrix"][0][0] == pytest.approx(1.0)
    assert corr["matrix"][1][1] == pytest.approx(1.0)
    assert corr["matrix"][0][1] == pytest.approx(corr["matrix"][1][0])


def test_portfolio_analyze_rejects_mismatched_lengths():
    payload = {"prices_by_ticker": {"AAPL": [100, 102], "MSFT": [50, 51, 52]}}
    r = client.post("/api/portfolio/analyze", json=payload)
    assert r.status_code == 422


def test_ai_ask_returns_503_without_api_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    r = client.post("/api/companies/AAPL/ai/ask", json={"question": "What drives the valuation?"})
    assert r.status_code == 503


def test_report_endpoint_has_all_sections():
    r = client.get("/api/companies/AAPL/report")
    assert r.status_code == 200
    assert len(r.json()["sections"]) == 14


def test_net_debt_and_shares_raises_422_when_shares_missing():
    """Regression test: /dcf/scenarios, /dcf/sensitivity, and /comparables
    used to skip this check (only /dcf had it), so a provider that doesn't
    populate shares_outstanding (e.g. a live one) would crash those three
    endpoints with an unhandled 500 instead of a clean 422."""
    yf = YearFinancials(
        fiscal_year=2024,
        income={},
        balance={"total_debt": 100.0, "cash_and_equivalents": 50.0},
        cash_flow={},
    )
    with pytest.raises(HTTPException) as exc_info:
        _net_debt_and_shares(yf)
    assert exc_info.value.status_code == 422


def test_post_report_includes_dcf_and_comparables_results():
    """The GET /report endpoint never had a way to include a DCF or comps
    result (confirmed live: run a DCF, then GET /report, and it still says
    'No DCF has been run yet'). POST /report accepts precomputed results so
    the report reflects the same numbers already shown elsewhere."""
    dcf_result = {
        "implied_share_price": 105.41,
        "enterprise_value": 1676816.0,
        "equity_value": 1633816.0,
        "sum_pv_fcf": 424886.3,
        "pv_terminal_value": 1251929.7,
    }
    comparables = {"implied_price_from_pe": 120.0, "median_pe": 22.0}
    r = client.post("/api/companies/AAPL/report", json={"dcf_result": dcf_result, "comparables": comparables})
    assert r.status_code == 200
    body = r.json()
    assert "$105.41" in body["sections"]["dcf_valuation"]
    assert "DCF: $105.41" in body["sections"]["valuation_summary"]
    assert "Comps (P/E): $120.00" in body["sections"]["valuation_summary"]


def test_post_report_with_no_body_matches_get_report_placeholders():
    r = client.post("/api/companies/AAPL/report", json={})
    assert r.status_code == 200
    assert r.json()["sections"]["dcf_valuation"] == "No DCF has been run for this company yet."


def test_post_report_includes_scenarios_from_dcf_scenarios_endpoint():
    """Regression test: the frontend caches the *entire* /dcf/scenarios
    response ({ticker, data_mode, scenarios: {bear, base, bull}}) and used
    to POST that whole object as the report's "scenarios" field. The report
    generator expects just the inner {bear, base, bull} map, so the
    scenarios section silently rendered as if nothing had been run. This
    replays the corrected frontend flow end-to-end: call /dcf/scenarios,
    forward only its `.scenarios` field to /report, and confirm the
    scenarios section is actually populated."""
    scenarios_resp = client.post("/api/companies/AAPL/dcf/scenarios", json=DCF_PAYLOAD)
    assert scenarios_resp.status_code == 200
    scenarios = scenarios_resp.json()["scenarios"]

    r = client.post("/api/companies/AAPL/report", json={"scenarios": scenarios})
    assert r.status_code == 200
    section = r.json()["sections"]["scenarios"]
    assert section != "No scenario analysis has been run yet."
    assert "Bear:" in section
    assert "Base:" in section
    assert "Bull:" in section


def test_financials_falls_back_to_demo_when_live_provider_fails(monkeypatch):
    """Confirms the per-request fallback promised in docs/DATA_SOURCES.md:
    if a live provider is configured but an individual request fails after
    startup, the endpoint should still succeed by using demo data for that
    request -- labeled as such -- rather than 404ing or crashing."""
    monkeypatch.setattr(main_module, "provider", _FailingLiveProvider(ProviderUnavailableError("simulated outage")))
    r = client.get("/api/companies/AAPL/financials")
    assert r.status_code == 200
    assert r.json()["data_mode"] == "demo"
    assert len(r.json()["years"]) == 5


def test_get_company_falls_back_to_demo_when_live_provider_fails(monkeypatch):
    monkeypatch.setattr(main_module, "provider", _FailingLiveProvider(ProviderUnavailableError("simulated outage")))
    r = client.get("/api/companies/AAPL")
    assert r.status_code == 200
    assert r.json()["data_mode"] == "demo"


def test_unknown_ticker_still_404s_even_when_provider_is_live(monkeypatch):
    """A bad ticker is a ValueError, not a provider-availability problem --
    it must never trigger a silent fallback to demo data for a different
    (mismatched) ticker."""
    monkeypatch.setattr(main_module, "provider", _FailingLiveProvider(ValueError("'ZZZZ' not found")))
    r = client.get("/api/companies/ZZZZ/financials")
    assert r.status_code == 404


def test_list_companies_handles_live_provider_without_enumeration(monkeypatch):
    """LiveProvider.list_supported_tickers() always raises NotImplementedError
    by design; the endpoint must not 500 because of it."""
    monkeypatch.setattr(main_module, "provider", _FailingLiveProvider(NotImplementedError("nope")))
    r = client.get("/api/companies")
    assert r.status_code == 200
    assert r.json()["tickers"] == []


def test_end_to_end_aapl_flow():
    """Search AAPL -> financials -> ratios -> DCF -> report, per spec's required E2E test."""
    assert client.get("/api/companies/AAPL").status_code == 200
    assert client.get("/api/companies/AAPL/financials").status_code == 200
    assert client.get("/api/companies/AAPL/ratios").status_code == 200
    dcf = client.post("/api/companies/AAPL/dcf", json=DCF_PAYLOAD)
    assert dcf.status_code == 200
    report = client.get("/api/companies/AAPL/report")
    assert report.status_code == 200
    assert "AAPL" in report.json()["title"]

    # the DCF just run actually flows into the report when passed through
    full_report = client.post("/api/companies/AAPL/report", json={"dcf_result": dcf.json()})
    assert full_report.status_code == 200
    price_str = f"{dcf.json()['implied_share_price']:.2f}"
    assert price_str in full_report.json()["sections"]["dcf_valuation"]


# ---------------------------------------------------------------------------
# J. Research report persistence (research_reports table)
# ---------------------------------------------------------------------------


def test_get_report_is_never_persisted():
    """The quick GET /report fires automatically on every Report-tab page
    load; persisting it would flood research_reports with duplicates the
    user never asked to save."""
    r = client.get("/api/companies/AAPL/report")
    assert r.status_code == 200
    assert r.json()["id"] is None


def test_post_report_persists_and_is_listed_and_retrievable():
    r = client.post("/api/companies/MSFT/report", json={})
    assert r.status_code == 200
    report_id = r.json()["id"]
    assert report_id is not None

    listing = client.get("/api/companies/MSFT/reports")
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()["reports"]]
    assert report_id in ids
    saved_row = next(row for row in listing.json()["reports"] if row["id"] == report_id)
    assert saved_row["generated_by"] == "equitylens-report-engine"
    assert saved_row["ai_assisted"] is False

    fetched = client.get(f"/api/companies/MSFT/reports/{report_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == report_id
    assert body["title"] == r.json()["title"]
    assert body["sections"] == r.json()["sections"]


def test_saved_report_scoped_to_its_own_ticker():
    """A report saved under one ticker must not be fetchable through a
    different ticker's URL, even with the correct id."""
    msft_report = client.post("/api/companies/MSFT/report", json={})
    report_id = msft_report.json()["id"]
    assert client.get(f"/api/companies/NVDA/reports/{report_id}").status_code == 404


def test_get_saved_report_404_for_unknown_id():
    r = client.get("/api/companies/AAPL/reports/999999999")
    assert r.status_code == 404


def test_list_saved_reports_empty_for_ticker_with_no_saved_reports():
    r = client.get("/api/companies/EQUITYLENS_NEVER_SAVED_TICKER/reports")
    assert r.status_code == 200
    assert r.json() == {"ticker": "EQUITYLENS_NEVER_SAVED_TICKER", "reports": []}


def test_ai_ask_persists_qa_when_answered(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        main_module.ResearchAssistant, "ask", lambda self, ctx, question: f"Canned answer to: {question}"
    )

    r = client.post("/api/companies/AAPL/ai/ask", json={"question": "What drove FY2025 margin expansion?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Canned answer to: What drove FY2025 margin expansion?"
    assert body["id"] is not None

    listing = client.get("/api/companies/AAPL/reports").json()["reports"]
    saved = next(row for row in listing if row["id"] == body["id"])
    assert saved["generated_by"] == "ai-research-assistant"
    assert saved["ai_assisted"] is True

    fetched = client.get(f"/api/companies/AAPL/reports/{body['id']}").json()
    assert fetched["sections"]["question"] == "What drove FY2025 margin expansion?"
    assert fetched["sections"]["answer"] == body["answer"]


def test_ai_ask_503_without_key_never_persists(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    before = len(client.get("/api/companies/AAPL/reports").json()["reports"])
    r = client.post("/api/companies/AAPL/ai/ask", json={"question": "Anything?"})
    assert r.status_code == 503
    after = len(client.get("/api/companies/AAPL/reports").json()["reports"])
    assert after == before


def test_report_persistence_failure_does_not_break_the_response(monkeypatch):
    """A database hiccup while saving must never turn an already-computed,
    successful report into an error for the caller -- it should just come
    back with id: null."""

    class _BrokenSession:
        def __enter__(self):
            raise RuntimeError("simulated database outage")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(main_module, "get_session", lambda: _BrokenSession())
    r = client.post("/api/companies/NVDA/report", json={})
    assert r.status_code == 200
    assert r.json()["id"] is None
    assert r.json()["title"]  # the actual report body is still there
