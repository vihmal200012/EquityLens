import pytest

from backend.financial_engine.ratios import (
    YearFinancials,
    compute_ratio_series,
    current_ratio,
    debt_to_equity,
    ebitda_margin,
    eps_growth,
    free_cash_flow,
    fcf_margin,
    gross_margin,
    net_debt_to_ebitda,
    net_margin,
    operating_margin,
    revenue_growth,
    roe,
    roic,
)


@pytest.fixture
def year_2024():
    # Hand-picked round numbers so every expected ratio can be verified by hand.
    return YearFinancials(
        fiscal_year=2024,
        income=dict(
            revenue=1000.0,
            cogs=600.0,
            gross_profit=400.0,
            operating_expenses=150.0,
            depreciation_amortization=50.0,
            ebit=200.0,          # 400 - 150 - 50
            ebitda=250.0,        # ebit + da
            interest_expense=20.0,
            pretax_income=180.0,
            tax_expense=36.0,    # 20% effective
            net_income=144.0,
            eps=1.44,
        ),
        balance=dict(
            cash_and_equivalents=100.0,
            total_current_assets=400.0,
            total_assets=1200.0,
            total_current_liabilities=200.0,
            total_debt=300.0,
            total_liabilities=600.0,
            total_equity=600.0,
            shares_outstanding=100.0,
        ),
        cash_flow=dict(
            net_income=144.0,
            depreciation_amortization=50.0,
            change_in_nwc=20.0,
            operating_cash_flow=174.0,   # 144 + 50 - 20
            capital_expenditures=60.0,
            free_cash_flow=114.0,        # 174 - 60
        ),
    )


@pytest.fixture
def year_2023():
    return YearFinancials(
        fiscal_year=2023,
        income=dict(revenue=800.0, eps=1.20, ebit=150.0, ebitda=190.0, net_income=100.0, pretax_income=125.0, tax_expense=25.0),
        balance=dict(total_debt=280.0, total_equity=520.0, cash_and_equivalents=90.0),
        cash_flow=dict(),
    )


def test_gross_margin(year_2024):
    assert gross_margin(year_2024) == pytest.approx(0.40)  # 400/1000


def test_operating_margin(year_2024):
    assert operating_margin(year_2024) == pytest.approx(0.20)  # 200/1000


def test_net_margin(year_2024):
    assert net_margin(year_2024) == pytest.approx(0.144)  # 144/1000


def test_ebitda_margin(year_2024):
    assert ebitda_margin(year_2024) == pytest.approx(0.25)  # 250/1000


def test_free_cash_flow_uses_reported_value_when_present(year_2024):
    assert free_cash_flow(year_2024) == pytest.approx(114.0)


def test_free_cash_flow_falls_back_to_ocf_minus_capex():
    yf = YearFinancials(
        fiscal_year=2024,
        income={},
        balance={},
        cash_flow=dict(operating_cash_flow=200.0, capital_expenditures=75.0),
    )
    assert free_cash_flow(yf) == pytest.approx(125.0)


def test_fcf_margin(year_2024):
    assert fcf_margin(year_2024) == pytest.approx(0.114)  # 114/1000


def test_roe(year_2024):
    assert roe(year_2024) == pytest.approx(144.0 / 600.0)  # 0.24


def test_roic(year_2024):
    # effective tax rate = 36/180 = 0.20; NOPAT = 200 * 0.80 = 160
    # invested capital = 300 + 600 - 100 = 800
    # ROIC = 160 / 800 = 0.20
    assert roic(year_2024) == pytest.approx(0.20)


def test_debt_to_equity(year_2024):
    assert debt_to_equity(year_2024) == pytest.approx(0.5)  # 300/600


def test_net_debt_to_ebitda(year_2024):
    # net debt = 300 - 100 = 200; 200/250 = 0.8
    assert net_debt_to_ebitda(year_2024) == pytest.approx(0.8)


def test_current_ratio(year_2024):
    assert current_ratio(year_2024) == pytest.approx(2.0)  # 400/200


def test_revenue_growth(year_2024, year_2023):
    # (1000 - 800) / 800 = 0.25
    assert revenue_growth(year_2024, year_2023) == pytest.approx(0.25)


def test_revenue_growth_none_without_prior(year_2024):
    assert revenue_growth(year_2024, None) is None


def test_eps_growth(year_2024, year_2023):
    # (1.44 - 1.20) / 1.20 = 0.20
    assert eps_growth(year_2024, year_2023) == pytest.approx(0.20)


def test_missing_line_item_returns_none_not_exception():
    yf = YearFinancials(fiscal_year=2024, income={}, balance={}, cash_flow={})
    assert gross_margin(yf) is None
    assert roe(yf) is None
    assert current_ratio(yf) is None


def test_zero_denominator_returns_none():
    yf = YearFinancials(
        fiscal_year=2024,
        income=dict(revenue=0.0, gross_profit=100.0),
        balance={},
        cash_flow={},
    )
    assert gross_margin(yf) is None


def test_compute_ratio_series_keys_by_fiscal_year(year_2024, year_2023):
    series = compute_ratio_series([year_2023, year_2024])
    assert set(series.keys()) == {2023, 2024}
    assert series[2024]["revenue_growth"] == pytest.approx(0.25)
    assert series[2023]["revenue_growth"] is None
