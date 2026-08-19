"""
EquityLens relational schema.

Tables map 1:1 to the domain spec:
    companies, financial_statements, market_data, ratios, valuations,
    valuation_assumptions, portfolio_positions, portfolio_snapshots,
    research_reports

Every row that represents a fact carries `source` and `retrieved_at` /
`created_at` provenance so the app can always distinguish real data from
demo data, and know when it was pulled.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DataSource(str, enum.Enum):
    """Where a row's numbers came from. Never silently mixed."""

    DEMO = "demo"          # static, clearly-labeled sample data
    LIVE_API = "live_api"  # a real FinancialDataProvider
    USER_INPUT = "user_input"   # analyst-entered assumption
    CALCULATED = "calculated"   # derived by EquityLens itself


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.DEMO)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    financial_statements: Mapped[list["FinancialStatement"]] = relationship(back_populates="company")
    market_data: Mapped[list["MarketData"]] = relationship(back_populates="company")
    ratios: Mapped[list["RatioSet"]] = relationship(back_populates="company")
    valuations: Mapped[list["Valuation"]] = relationship(back_populates="company")


class StatementType(str, enum.Enum):
    INCOME = "income_statement"
    BALANCE = "balance_sheet"
    CASH_FLOW = "cash_flow"


class FinancialStatement(Base):
    """One fiscal-period statement. Line items live in `data` (JSON) so the
    schema doesn't need to change if a provider adds/removes a line item;
    calculated ratios always read named keys defensively (see ratios.py)."""

    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("company_id", "statement_type", "fiscal_year", "period", name="uq_statement_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    statement_type: Mapped[StatementType] = mapped_column(Enum(StatementType))
    fiscal_year: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String(4), default="FY")  # FY, Q1..Q4
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    data: Mapped[dict] = mapped_column(JSON)  # line items, in absolute currency units
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.DEMO)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="financial_statements")


class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = (UniqueConstraint("company_id", "as_of_date", name="uq_market_data_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[float] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    enterprise_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.DEMO)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="market_data")


class RatioSet(Base):
    """A computed bundle of ratios for one fiscal year. Always source=CALCULATED —
    ratios are derived by EquityLens, never fetched, so provenance is fixed."""

    __tablename__ = "ratios"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", name="uq_ratio_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)  # {"gross_margin": 0.43, ...}
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.CALCULATED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="ratios")


class ValuationAssumptions(Base):
    """A named, versioned set of DCF inputs. Scenarios (bear/base/bull) are
    just multiple rows pointing at the same valuation."""

    __tablename__ = "valuation_assumptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valuation_id: Mapped[int] = mapped_column(ForeignKey("valuations.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(20))  # bear | base | bull
    revenue_growth_rates: Mapped[list] = mapped_column(JSON)  # one rate per forecast year
    ebit_margin: Mapped[float] = mapped_column(Float)
    tax_rate: Mapped[float] = mapped_column(Float)
    da_pct_revenue: Mapped[float] = mapped_column(Float)
    capex_pct_revenue: Mapped[float] = mapped_column(Float)
    nwc_pct_revenue_change: Mapped[float] = mapped_column(Float)
    wacc: Mapped[float] = mapped_column(Float)
    terminal_growth: Mapped[float] = mapped_column(Float)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.USER_INPUT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    valuation: Mapped["Valuation"] = relationship(back_populates="assumptions")


class Valuation(Base):
    """A versioned valuation run. Re-running with new assumptions creates a
    new row rather than overwriting — this is what 'versioned valuation
    models' in the spec means in practice."""

    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    method: Mapped[str] = mapped_column(String(30), default="DCF")  # DCF | Comparables
    results: Mapped[dict] = mapped_column(JSON)  # implied price, EV, equity value per scenario
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="valuations")
    assumptions: Mapped[list["ValuationAssumptions"]] = relationship(back_populates="valuation")


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(String(50), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    weight: Mapped[float] = mapped_column(Float)  # 0..1, of portfolio at entry
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime)
    entry_price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PortfolioSnapshot(Base):
    """Daily (or periodic) portfolio value, used to compute return/vol/Sharpe/drawdown."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("portfolio_id", "as_of_date", name="uq_portfolio_snapshot_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(String(50), index=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime)
    total_value: Mapped[float] = mapped_column(Float)
    daily_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource), default=DataSource.CALCULATED)


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    valuation_id: Mapped[int | None] = mapped_column(ForeignKey("valuations.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    sections: Mapped[dict] = mapped_column(JSON)  # {"executive_summary": "...", ...}
    generated_by: Mapped[str] = mapped_column(String(50), default="equitylens-report-engine")
    ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
