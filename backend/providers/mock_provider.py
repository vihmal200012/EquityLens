"""
MockProvider — DEMO MODE data source.

IMPORTANT: The figures below are synthetic, illustrative financial data
built to be internally consistent (balance sheets balance, cash flow ties
to income statement, etc.) so the modeling engine has something real to
chew on. They are loosely scaled to the approximate size of the named
companies for realism, but they are NOT the companies' actual reported
GAAP filings. Every record produced by this provider is tagged
source="demo" end-to-end (DB row, API response, and AI context), and the
frontend must render a persistent "DEMO DATA — not live financials"
banner whenever source == demo. Swap in a real provider (e.g. an
Alpha Vantage / Financial Modeling Prep adapter implementing the same
FinancialDataProvider interface) and nothing else in the app has to change.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.providers.base import (
    CompanyProfile,
    FinancialDataProvider,
    MarketQuote,
    StatementPeriod,
)

# Base-year (most recent fiscal year) figures in $ millions, and a
# per-company growth/margin profile used to synthesize 5 years of history
# by walking backwards from the base year. This keeps every statement
# internally consistent instead of hand-typing 5 years x 3 statements x
# N companies of unrelated numbers.
_PROFILES = {
    "AAPL": dict(
        name="Apple Inc. (demo data)",
        sector="Technology",
        industry="Consumer Electronics",
        description=(
            "Illustrative demo profile modeled on a large diversified consumer-electronics "
            "and services company. Not sourced from Apple's actual filings."
        ),
        shares_outstanding=15_500.0,  # millions
        base_revenue=390_000.0,
        revenue_cagr_hist=0.06,
        gross_margin=0.45,
        opex_pct_rev=0.14,
        da_pct_rev=0.028,
        capex_pct_rev=0.031,
        tax_rate=0.15,
        cash=62_000.0,
        total_debt=105_000.0,
        interest_rate_on_debt=0.035,
    ),
    "MSFT": dict(
        name="Microsoft Corp. (demo data)",
        sector="Technology",
        industry="Software Infrastructure",
        description=(
            "Illustrative demo profile modeled on a large diversified software and cloud "
            "infrastructure company. Not sourced from Microsoft's actual filings."
        ),
        shares_outstanding=7_430.0,
        base_revenue=245_000.0,
        revenue_cagr_hist=0.14,
        gross_margin=0.69,
        opex_pct_rev=0.24,
        da_pct_rev=0.045,
        capex_pct_rev=0.11,
        tax_rate=0.18,
        cash=78_000.0,
        total_debt=48_000.0,
        interest_rate_on_debt=0.032,
    ),
    "NVDA": dict(
        name="NVIDIA Corp. (demo data)",
        sector="Technology",
        industry="Semiconductors",
        description=(
            "Illustrative demo profile modeled on a fast-growing semiconductor / accelerated-"
            "computing company. Not sourced from NVIDIA's actual filings."
        ),
        shares_outstanding=24_500.0,
        base_revenue=96_000.0,
        revenue_cagr_hist=0.55,
        gross_margin=0.75,
        opex_pct_rev=0.12,
        da_pct_rev=0.02,
        capex_pct_rev=0.035,
        tax_rate=0.13,
        cash=25_000.0,
        total_debt=9_500.0,
        interest_rate_on_debt=0.03,
    ),
}


def _synthesize_years(profile: dict, years: int) -> list[dict]:
    """Walk backwards `years` fiscal years from the base year, applying a
    slightly decaying growth rate as we go further back, and derive a
    consistent income statement / balance sheet / cash flow for each year."""
    rows = []
    revenue = profile["base_revenue"]
    debt = profile["total_debt"]
    cash = profile["cash"]
    current_year = datetime.now(timezone.utc).year - 1  # most recently completed FY

    for i in range(years):
        fy = current_year - i
        gm = profile["gross_margin"]
        cogs = revenue * (1 - gm)
        gross_profit = revenue - cogs
        opex = revenue * profile["opex_pct_rev"]
        da = revenue * profile["da_pct_rev"]
        ebit = gross_profit - opex - da
        interest_expense = debt * profile["interest_rate_on_debt"]
        pretax_income = ebit - interest_expense
        tax = max(pretax_income, 0) * profile["tax_rate"]
        net_income = pretax_income - tax

        capex = revenue * profile["capex_pct_rev"]
        # NWC change modeled as a small function of revenue growth
        nwc_change = revenue * 0.015 if i < years - 1 else revenue * 0.01
        operating_cash_flow = net_income + da - nwc_change
        free_cash_flow = operating_cash_flow - capex

        total_assets = revenue * 1.6 + cash
        total_liabilities = debt + revenue * 0.35
        total_equity = total_assets - total_liabilities
        current_assets = revenue * 0.55 + cash
        current_liabilities = revenue * 0.30

        rows.append(
            dict(
                fiscal_year=fy,
                income_statement=dict(
                    revenue=round(revenue, 1),
                    cogs=round(cogs, 1),
                    gross_profit=round(gross_profit, 1),
                    operating_expenses=round(opex, 1),
                    depreciation_amortization=round(da, 1),
                    ebit=round(ebit, 1),
                    ebitda=round(ebit + da, 1),
                    interest_expense=round(interest_expense, 1),
                    pretax_income=round(pretax_income, 1),
                    tax_expense=round(tax, 1),
                    net_income=round(net_income, 1),
                    eps=round(net_income / profile["shares_outstanding"], 4),
                ),
                balance_sheet=dict(
                    cash_and_equivalents=round(cash, 1),
                    total_current_assets=round(current_assets, 1),
                    total_assets=round(total_assets, 1),
                    total_current_liabilities=round(current_liabilities, 1),
                    total_debt=round(debt, 1),
                    total_liabilities=round(total_liabilities, 1),
                    total_equity=round(total_equity, 1),
                    shares_outstanding=profile["shares_outstanding"],
                ),
                cash_flow=dict(
                    net_income=round(net_income, 1),
                    depreciation_amortization=round(da, 1),
                    change_in_nwc=round(nwc_change, 1),
                    operating_cash_flow=round(operating_cash_flow, 1),
                    capital_expenditures=round(capex, 1),
                    free_cash_flow=round(free_cash_flow, 1),
                ),
            )
        )

        # step backwards for next (older) year
        decay = max(profile["revenue_cagr_hist"] - 0.015 * i, 0.02)
        revenue = revenue / (1 + decay)
        debt = debt * 0.97
        cash = cash * 0.95

    return rows


class MockProvider(FinancialDataProvider):
    """DEMO MODE provider. No network calls, no API key required."""

    name = "demo"

    def __init__(self) -> None:
        self._cache: dict[str, list[dict]] = {}

    def _years(self, ticker: str, years: int) -> list[dict]:
        ticker = ticker.upper()
        if ticker not in _PROFILES:
            raise ValueError(
                f"'{ticker}' is not in the demo dataset. Supported demo tickers: "
                f"{', '.join(_PROFILES)}"
            )
        key = f"{ticker}:{years}"
        if key not in self._cache:
            self._cache[key] = _synthesize_years(_PROFILES[ticker], years)
        return self._cache[key]

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        ticker = ticker.upper()
        if ticker not in _PROFILES:
            raise ValueError(
                f"'{ticker}' is not in the demo dataset. Supported demo tickers: "
                f"{', '.join(_PROFILES)}"
            )
        p = _PROFILES[ticker]
        return CompanyProfile(
            ticker=ticker,
            name=p["name"],
            sector=p["sector"],
            industry=p["industry"],
            description=p["description"],
            currency="USD",
            shares_outstanding=p["shares_outstanding"],
            source="demo",
        )

    def get_income_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return [
            StatementPeriod(fiscal_year=row["fiscal_year"], period="FY", data=row["income_statement"], source="demo")
            for row in self._years(ticker, years)
        ]

    def get_balance_sheets(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return [
            StatementPeriod(fiscal_year=row["fiscal_year"], period="FY", data=row["balance_sheet"], source="demo")
            for row in self._years(ticker, years)
        ]

    def get_cash_flow_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        return [
            StatementPeriod(fiscal_year=row["fiscal_year"], period="FY", data=row["cash_flow"], source="demo")
            for row in self._years(ticker, years)
        ]

    def get_market_quote(self, ticker: str) -> MarketQuote:
        years = self._years(ticker, 1)
        latest = years[0]
        profile = _PROFILES[ticker.upper()]
        net_income = latest["income_statement"]["net_income"]
        # crude illustrative P/E of 28x to derive a demo price — clearly a
        # simplification, not a market quote.
        implied_price = (net_income * 28) / profile["shares_outstanding"]
        market_cap = implied_price * profile["shares_outstanding"]
        ev = market_cap + latest["balance_sheet"]["total_debt"] - latest["balance_sheet"]["cash_and_equivalents"]
        return MarketQuote(
            as_of_date=datetime.now(timezone.utc),
            price=round(implied_price, 2),
            market_cap=round(market_cap, 1),
            enterprise_value=round(ev, 1),
            volume=None,
            source="demo",
        )

    def list_supported_tickers(self) -> list[str]:
        return sorted(_PROFILES.keys())
