import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)

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
