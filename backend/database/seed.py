"""
Seeds the database with the demo-mode companies and their statements, so
the app has data to show on first run without hitting any API.

Usage:
    python -m backend.database.seed
"""
from __future__ import annotations

from backend.database.models import Company, DataSource, FinancialStatement, StatementType
from backend.database.session import get_session, init_db
from backend.providers.mock_provider import MockProvider


def seed() -> None:
    init_db()
    provider = MockProvider()

    with get_session() as session:
        for ticker in provider.list_supported_tickers():
            existing = session.query(Company).filter_by(ticker=ticker).one_or_none()
            if existing:
                print(f"{ticker} already seeded, skipping.")
                continue

            profile = provider.get_company_profile(ticker)
            company = Company(
                ticker=profile.ticker,
                name=profile.name,
                sector=profile.sector,
                industry=profile.industry,
                description=profile.description,
                currency=profile.currency,
                shares_outstanding=profile.shares_outstanding,
                source=DataSource.DEMO,
            )
            session.add(company)
            session.flush()  # get company.id

            for stmt_type, fetch in (
                (StatementType.INCOME, provider.get_income_statements),
                (StatementType.BALANCE, provider.get_balance_sheets),
                (StatementType.CASH_FLOW, provider.get_cash_flow_statements),
            ):
                for period in fetch(ticker, 5):
                    session.add(
                        FinancialStatement(
                            company_id=company.id,
                            statement_type=stmt_type,
                            fiscal_year=period.fiscal_year,
                            period=period.period,
                            data=period.data,
                            source=DataSource.DEMO,
                        )
                    )
            print(f"Seeded {ticker}: {profile.name}")


if __name__ == "__main__":
    seed()
