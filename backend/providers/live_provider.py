"""
LiveProvider — real-data adapter for a Financial-Modeling-Prep-style REST API.

Requires FINANCIAL_API_KEY to be set; if it isn't, raises
ProviderUnavailableError rather than ever returning fabricated numbers.

Vendor payloads come back in FMP's own field names (camelCase, e.g.
"totalDebt", "operatingIncome") and, for cash flow items, FMP's own sign
convention (capital expenditure and working-capital change reported as
negative cash-outflow numbers). Every engine in this app (ratios.py,
dcf.py) reads the internal snake_case schema defined by
providers/mock_provider.py's synthetic statements (e.g. "total_debt",
"ebit"), with capex/NWC-change stored as positive magnitudes that formulas
explicitly subtract. The `_INCOME_STATEMENT_MAP` / `_BALANCE_SHEET_MAP` /
`_CASH_FLOW_MAP` dicts below translate vendor keys to that internal schema;
`_normalize_cash_flow` additionally fixes the sign convention. Swap the
BASE_URL / endpoint paths and these maps for whatever real provider you
have a key for — the shape of the interface (base.py) and the internal
line-item schema are what the rest of the app depends on, not this vendor.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from backend.providers.base import (
    CompanyProfile,
    FinancialDataProvider,
    MarketQuote,
    ProviderUnavailableError,
    StatementPeriod,
)

BASE_URL = "https://financialmodelingprep.com/api/v3"

logger = logging.getLogger("equitylens.providers")

# Vendor key -> internal snake_case key. Only mapped keys are carried over;
# an unmapped or null vendor field is simply absent from the result, and
# every ratio/DCF function already treats a missing key as `None` (see
# ratios.py's `_safe_div`) rather than raising.
_INCOME_STATEMENT_MAP = {
    "revenue": "revenue",
    "costOfRevenue": "cogs",
    "grossProfit": "gross_profit",
    "operatingExpenses": "operating_expenses",
    "depreciationAndAmortization": "depreciation_amortization",
    "operatingIncome": "ebit",
    "ebitda": "ebitda",
    "interestExpense": "interest_expense",
    "incomeBeforeTax": "pretax_income",
    "incomeTaxExpense": "tax_expense",
    "netIncome": "net_income",
    "epsdiluted": "eps",
}

_BALANCE_SHEET_MAP = {
    "cashAndCashEquivalents": "cash_and_equivalents",
    "totalCurrentAssets": "total_current_assets",
    "totalAssets": "total_assets",
    "totalCurrentLiabilities": "total_current_liabilities",
    "totalDebt": "total_debt",
    "totalLiabilities": "total_liabilities",
    "totalStockholdersEquity": "total_equity",
}

_CASH_FLOW_MAP = {
    "netIncome": "net_income",
    "depreciationAndAmortization": "depreciation_amortization",
    "changeInWorkingCapital": "change_in_nwc",
    "operatingCashFlow": "operating_cash_flow",
    "capitalExpenditure": "capital_expenditures",
    "freeCashFlow": "free_cash_flow",
}


def _normalize(row: dict, field_map: dict[str, str]) -> dict:
    out = {}
    for vendor_key, internal_key in field_map.items():
        v = row.get(vendor_key)
        if v is not None:
            out[internal_key] = float(v)
    return out


def _normalize_cash_flow(row: dict) -> dict:
    out = _normalize(row, _CASH_FLOW_MAP)
    # FMP reports capex and the working-capital line as negative (cash
    # outflow); the internal schema uses positive magnitudes (see
    # mock_provider.py), which formulas explicitly subtract.
    if "capital_expenditures" in out:
        out["capital_expenditures"] = abs(out["capital_expenditures"])
    if "change_in_nwc" in out:
        out["change_in_nwc"] = -out["change_in_nwc"]
    return out


class LiveProvider(FinancialDataProvider):
    name = "live_api"

    def __init__(self) -> None:
        self.api_key = os.environ.get("FINANCIAL_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderUnavailableError(
                "FINANCIAL_API_KEY is not set. Configure it in your .env file, "
                "or use MockProvider for DEMO MODE."
            )
        self._shares_cache: dict[str, float | None] = {}

    def _get(self, path: str, **params) -> dict | list:
        params["apikey"] = self.api_key
        try:
            resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderUnavailableError(f"Live provider request failed: {exc}") from exc
        return resp.json()

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        data = self._get(f"profile/{ticker.upper()}")
        if not data:
            raise ProviderUnavailableError(f"No profile returned for {ticker}")
        row = data[0]

        shares_out = row.get("sharesOutstanding")
        if not shares_out:
            mkt_cap, price = row.get("mktCap"), row.get("price")
            if mkt_cap and price:
                shares_out = mkt_cap / price

        return CompanyProfile(
            ticker=ticker.upper(),
            name=row.get("companyName", ticker.upper()),
            sector=row.get("sector", "Unknown"),
            industry=row.get("industry", "Unknown"),
            description=row.get("description", ""),
            currency=row.get("currency", "USD"),
            shares_outstanding=float(shares_out or 0),
            source="live_api",
        )

    def _shares_outstanding(self, ticker: str) -> float | None:
        """Balance-sheet-statement doesn't carry shares outstanding on an
        FMP-style API -- it lives on the profile endpoint. Cached per
        instance so every balance-sheet year doesn't trigger its own
        profile request."""
        key = ticker.upper()
        if key not in self._shares_cache:
            try:
                profile = self.get_company_profile(ticker)
                self._shares_cache[key] = profile.shares_outstanding or None
            except ProviderUnavailableError:
                self._shares_cache[key] = None
        return self._shares_cache[key]

    def _statements(self, path: str, ticker: str, years: int, normalize) -> list[StatementPeriod]:
        data = self._get(f"{path}/{ticker.upper()}", limit=years)
        out = []
        for row in data:
            fy = int(str(row.get("date", "0000"))[:4])
            out.append(StatementPeriod(fiscal_year=fy, period="FY", data=normalize(row), source="live_api"))
        return out

    def get_income_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return self._statements(
            "income-statement", ticker, years, lambda row: _normalize(row, _INCOME_STATEMENT_MAP)
        )

    def get_balance_sheets(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        shares = self._shares_outstanding(ticker)

        def normalize(row: dict) -> dict:
            out = _normalize(row, _BALANCE_SHEET_MAP)
            if shares:
                out["shares_outstanding"] = shares
            return out

        return self._statements("balance-sheet-statement", ticker, years, normalize)

    def get_cash_flow_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return self._statements("cash-flow-statement", ticker, years, _normalize_cash_flow)

    def get_market_quote(self, ticker: str) -> MarketQuote:
        data = self._get(f"quote/{ticker.upper()}")
        if not data:
            raise ProviderUnavailableError(f"No quote returned for {ticker}")
        row = data[0]

        shares_out = row.get("sharesOutstanding")
        if shares_out:
            self._shares_cache[ticker.upper()] = float(shares_out)

        return MarketQuote(
            as_of_date=datetime.now(timezone.utc),
            price=float(row.get("price") or 0),
            market_cap=float(row.get("marketCap") or 0) or None,
            enterprise_value=None,
            volume=float(row.get("volume") or 0) or None,
            source="live_api",
        )

    def list_supported_tickers(self) -> list[str]:
        # A real integration would call a /stock/list style endpoint.
        # Left unimplemented deliberately rather than guessing.
        raise NotImplementedError("LiveProvider does not enumerate all tickers; search by ticker directly.")


def get_provider() -> FinancialDataProvider:
    """Factory: use LiveProvider if FINANCIAL_API_KEY is configured and a
    key is present, otherwise fall back to MockProvider (DEMO MODE). This
    initial choice is resolved once at startup and only checks that a key
    string is configured, not that the vendor API is currently reachable --
    a later network failure, bad key, or rate limit on an individual
    request is handled per-request by the API layer (see
    backend/api/main.py's `_with_live_fallback`), which falls back to demo
    data for that one request and labels the response accordingly rather
    than crashing or silently mislabeling demo data as live."""
    from backend.providers.mock_provider import MockProvider

    if os.environ.get("FINANCIAL_API_KEY", "").strip():
        try:
            return LiveProvider()
        except ProviderUnavailableError as exc:
            logger.warning("Live provider unavailable (%s); falling back to DEMO MODE.", exc)
            return MockProvider()

    logger.info("FINANCIAL_API_KEY not set; running in DEMO MODE with synthetic data.")
    return MockProvider()
