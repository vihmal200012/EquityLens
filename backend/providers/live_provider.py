"""
LiveProvider — real-data adapter skeleton.

This implements the FinancialDataProvider interface against a generic
Financial-Modeling-Prep-style REST API (income-statement / balance-sheet /
cash-flow-statement / quote endpoints). It requires FINANCIAL_API_KEY to be
set; if it isn't, it raises ProviderUnavailableError rather than ever
returning fabricated numbers. Swap the BASE_URL / endpoint paths for
whatever real provider you have a key for — the shape of the interface
(base.py) is what the rest of the app depends on, not this vendor.
"""
from __future__ import annotations

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


class LiveProvider(FinancialDataProvider):
    name = "live_api"

    def __init__(self) -> None:
        self.api_key = os.environ.get("FINANCIAL_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderUnavailableError(
                "FINANCIAL_API_KEY is not set. Configure it in your .env file, "
                "or use MockProvider for DEMO MODE."
            )

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
        return CompanyProfile(
            ticker=ticker.upper(),
            name=row.get("companyName", ticker.upper()),
            sector=row.get("sector", "Unknown"),
            industry=row.get("industry", "Unknown"),
            description=row.get("description", ""),
            currency=row.get("currency", "USD"),
            shares_outstanding=float(row.get("sharesOutstanding") or 0),
            source="live_api",
        )

    def _statements(self, path: str, ticker: str, years: int) -> list[StatementPeriod]:
        data = self._get(f"{path}/{ticker.upper()}", limit=years)
        out = []
        for row in data:
            fy = int(str(row.get("date", "0000"))[:4])
            out.append(StatementPeriod(fiscal_year=fy, period="FY", data=row))
        return out

    def get_income_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return self._statements("income-statement", ticker, years)

    def get_balance_sheets(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return self._statements("balance-sheet-statement", ticker, years)

    def get_cash_flow_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return self._statements("cash-flow-statement", ticker, years)

    def get_market_quote(self, ticker: str) -> MarketQuote:
        data = self._get(f"quote/{ticker.upper()}")
        if not data:
            raise ProviderUnavailableError(f"No quote returned for {ticker}")
        row = data[0]
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
    """Factory: use LiveProvider if FINANCIAL_API_KEY is configured and
    reachable, otherwise fall back to MockProvider (DEMO MODE). The
    fallback is explicit and logged — never silent."""
    import logging

    from backend.providers.mock_provider import MockProvider

    logger = logging.getLogger("equitylens.providers")

    if os.environ.get("FINANCIAL_API_KEY", "").strip():
        try:
            return LiveProvider()
        except ProviderUnavailableError as exc:
            logger.warning("Live provider unavailable (%s); falling back to DEMO MODE.", exc)
            return MockProvider()

    logger.info("FINANCIAL_API_KEY not set; running in DEMO MODE with synthetic data.")
    return MockProvider()
