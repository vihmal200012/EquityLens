"""
LiveProvider tests: mocks requests.get to return canned FMP-shaped JSON
(no real network call, no key required) and verifies the vendor payload is
correctly mapped onto the internal snake_case schema every engine
(ratios.py, dcf.py) actually reads -- this is the gap the original
skeleton left ("not validated against a live key/response").
"""
import pytest
import requests
from unittest.mock import MagicMock, patch

from backend.providers.base import ProviderUnavailableError
from backend.providers.live_provider import LiveProvider

PROFILE = [
    {
        "symbol": "AAPL",
        "companyName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "description": "Demo description.",
        "currency": "USD",
        "sharesOutstanding": 15_500_000_000,
        "mktCap": 2_500_000_000_000,
        "price": 161.29,
    }
]

PROFILE_NO_SHARES_FIELD = [{**PROFILE[0], "sharesOutstanding": None}]

INCOME = [
    {
        "date": "2024-09-28",
        "revenue": 391_000_000_000,
        "costOfRevenue": 210_000_000_000,
        "grossProfit": 181_000_000_000,
        "operatingExpenses": 55_000_000_000,
        "depreciationAndAmortization": 11_000_000_000,
        "operatingIncome": 126_000_000_000,
        "ebitda": 137_000_000_000,
        "interestExpense": 3_900_000_000,
        "incomeBeforeTax": 123_000_000_000,
        "incomeTaxExpense": 18_000_000_000,
        "netIncome": 105_000_000_000,
        "epsdiluted": 6.75,
    }
]

BALANCE = [
    {
        "date": "2024-09-28",
        "cashAndCashEquivalents": 30_000_000_000,
        "totalCurrentAssets": 150_000_000_000,
        "totalAssets": 350_000_000_000,
        "totalCurrentLiabilities": 130_000_000_000,
        "totalDebt": 100_000_000_000,
        "totalLiabilities": 260_000_000_000,
        "totalStockholdersEquity": 90_000_000_000,
        # deliberately no shares-outstanding field -- FMP's balance-sheet
        # endpoint doesn't carry one; it lives on the profile endpoint.
    }
]

CASH_FLOW = [
    {
        "date": "2024-09-28",
        "netIncome": 105_000_000_000,
        "depreciationAndAmortization": 11_000_000_000,
        "changeInWorkingCapital": -5_000_000_000,
        "operatingCashFlow": 118_000_000_000,
        "capitalExpenditure": -10_000_000_000,
        "freeCashFlow": 108_000_000_000,
    }
]

QUOTE = [
    {
        "symbol": "AAPL",
        "price": 161.29,
        "marketCap": 2_500_000_000_000,
        "volume": 50_000_000,
        "sharesOutstanding": 15_500_000_000,
    }
]


def _fake_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def _fake_get(profile=PROFILE):
    def handler(url, params=None, timeout=None):
        if "/profile/" in url:
            return _fake_response(profile)
        if "/income-statement/" in url:
            return _fake_response(INCOME)
        if "/balance-sheet-statement/" in url:
            return _fake_response(BALANCE)
        if "/cash-flow-statement/" in url:
            return _fake_response(CASH_FLOW)
        if "/quote/" in url:
            return _fake_response(QUOTE)
        raise AssertionError(f"unexpected URL: {url}")

    return handler


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("FINANCIAL_API_KEY", "test-key")
    return LiveProvider()


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("FINANCIAL_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailableError):
        LiveProvider()


def test_income_statement_maps_vendor_keys_to_internal_schema(live):
    with patch("backend.providers.live_provider.requests.get", side_effect=_fake_get()):
        stmts = live.get_income_statements("AAPL", years=1)
    row = stmts[0].data
    assert row["revenue"] == 391_000_000_000
    assert row["cogs"] == 210_000_000_000
    assert row["gross_profit"] == 181_000_000_000
    assert row["ebit"] == 126_000_000_000
    assert row["ebitda"] == 137_000_000_000
    assert row["pretax_income"] == 123_000_000_000
    assert row["tax_expense"] == 18_000_000_000
    assert row["net_income"] == 105_000_000_000
    assert row["eps"] == 6.75
    assert stmts[0].source == "live_api"
    assert stmts[0].fiscal_year == 2024


def test_balance_sheet_injects_shares_outstanding_from_profile(live):
    """The FMP balance-sheet endpoint has no shares_outstanding field at
    all -- confirmed by omission from BALANCE above. Before this fix,
    `latest.balance.get("shares_outstanding")` would always be None
    against live data, which /dcf and friends now correctly reject with a
    422 (see test_api.py) instead of crashing -- but the real fix is that
    it should be populated in the first place, via the profile endpoint."""
    with patch("backend.providers.live_provider.requests.get", side_effect=_fake_get()):
        stmts = live.get_balance_sheets("AAPL", years=1)
    row = stmts[0].data
    assert row["cash_and_equivalents"] == 30_000_000_000
    assert row["total_debt"] == 100_000_000_000
    assert row["total_equity"] == 90_000_000_000
    assert row["shares_outstanding"] == 15_500_000_000


def test_cash_flow_fixes_fmp_sign_convention(live):
    """FMP reports capex and the working-capital change as negative (cash
    outflow); the internal schema uses positive magnitudes that formulas
    explicitly subtract (see mock_provider.py's own convention)."""
    with patch("backend.providers.live_provider.requests.get", side_effect=_fake_get()):
        stmts = live.get_cash_flow_statements("AAPL", years=1)
    row = stmts[0].data
    assert row["capital_expenditures"] == 10_000_000_000  # abs(-10e9)
    assert row["change_in_nwc"] == 5_000_000_000  # -(-5e9)
    assert row["free_cash_flow"] == 108_000_000_000


def test_mapped_statements_feed_ratio_engine_correctly(live):
    """End-to-end: the mapped output must actually be consumable by
    ratios.py, not just structurally present under the right key names."""
    from backend.financial_engine.ratios import YearFinancials, ebitda_margin, gross_margin, roic

    with patch("backend.providers.live_provider.requests.get", side_effect=_fake_get()):
        inc = live.get_income_statements("AAPL", years=1)[0].data
        bal = live.get_balance_sheets("AAPL", years=1)[0].data
        cf = live.get_cash_flow_statements("AAPL", years=1)[0].data

    yf = YearFinancials(fiscal_year=2024, income=inc, balance=bal, cash_flow=cf)
    assert gross_margin(yf) == pytest.approx(181 / 391, rel=1e-3)
    assert ebitda_margin(yf) == pytest.approx(137 / 391, rel=1e-3)
    assert roic(yf) is not None


def test_profile_falls_back_to_market_cap_over_price_when_shares_field_absent(live):
    with patch("backend.providers.live_provider.requests.get", side_effect=_fake_get(profile=PROFILE_NO_SHARES_FIELD)):
        profile = live.get_company_profile("AAPL")
    expected = PROFILE[0]["mktCap"] / PROFILE[0]["price"]
    assert profile.shares_outstanding == pytest.approx(expected)


def test_network_failure_raises_provider_unavailable(live):
    with patch("backend.providers.live_provider.requests.get", side_effect=requests.exceptions.ConnectionError("boom")):
        with pytest.raises(ProviderUnavailableError):
            live.get_income_statements("AAPL", years=1)


def test_list_supported_tickers_not_implemented(live):
    with pytest.raises(NotImplementedError):
        live.list_supported_tickers()
