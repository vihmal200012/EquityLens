"""
Provider abstraction.

Every data source (a paid API, a free API, static demo data) implements
this same interface. The rest of the app never talks to a vendor SDK
directly — it talks to a FinancialDataProvider. This is what lets
EquityLens run in DEMO MODE with zero API keys and swap in a real
provider later with no changes anywhere else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CompanyProfile:
    ticker: str
    name: str
    sector: str
    industry: str
    description: str
    currency: str
    shares_outstanding: float
    source: str  # "demo" | "live_api"


@dataclass
class StatementPeriod:
    fiscal_year: int
    period: str  # "FY"
    data: dict = field(default_factory=dict)
    source: str = "unknown"  # "demo" | "live_api" — which provider produced this record


@dataclass
class MarketQuote:
    as_of_date: datetime
    price: float
    market_cap: float | None
    enterprise_value: float | None
    volume: float | None
    source: str


class ProviderUnavailableError(RuntimeError):
    """Raised when a live provider is selected but has no credentials, or
    the upstream API call fails. Callers should fall back to DEMO MODE
    explicitly rather than silently substituting numbers."""


class FinancialDataProvider(ABC):
    """Adapter interface every data source must implement."""

    name: str = "base"

    @abstractmethod
    def get_company_profile(self, ticker: str) -> CompanyProfile:
        ...

    @abstractmethod
    def get_income_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        ...

    @abstractmethod
    def get_balance_sheets(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        ...

    @abstractmethod
    def get_cash_flow_statements(self, ticker: str, years: int = 5) -> list[StatementPeriod]:
        ...

    @abstractmethod
    def get_market_quote(self, ticker: str) -> MarketQuote:
        ...

    @abstractmethod
    def list_supported_tickers(self) -> list[str]:
        ...
