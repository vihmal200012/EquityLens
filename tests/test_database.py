import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Company, DataSource, FinancialStatement, StatementType


def make_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_and_query_company():
    session = make_test_session()
    company = Company(ticker="AAPL", name="Apple Inc. (demo data)", sector="Technology", source=DataSource.DEMO)
    session.add(company)
    session.commit()

    fetched = session.query(Company).filter_by(ticker="AAPL").one()
    assert fetched.name == "Apple Inc. (demo data)"
    assert fetched.source == DataSource.DEMO


def test_financial_statement_unique_constraint():
    session = make_test_session()
    company = Company(ticker="MSFT", name="Microsoft (demo)")
    session.add(company)
    session.commit()

    stmt1 = FinancialStatement(
        company_id=company.id,
        statement_type=StatementType.INCOME,
        fiscal_year=2024,
        period="FY",
        data={"revenue": 1000},
        source=DataSource.DEMO,
    )
    session.add(stmt1)
    session.commit()

    dupe = FinancialStatement(
        company_id=company.id,
        statement_type=StatementType.INCOME,
        fiscal_year=2024,
        period="FY",
        data={"revenue": 1100},
        source=DataSource.DEMO,
    )
    session.add(dupe)
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()


def test_company_financial_statements_relationship():
    session = make_test_session()
    company = Company(ticker="NVDA", name="NVIDIA (demo)")
    session.add(company)
    session.commit()

    session.add(
        FinancialStatement(
            company_id=company.id,
            statement_type=StatementType.BALANCE,
            fiscal_year=2024,
            data={"total_assets": 5000},
        )
    )
    session.commit()
    session.refresh(company)
    assert len(company.financial_statements) == 1
    assert company.financial_statements[0].statement_type == StatementType.BALANCE
