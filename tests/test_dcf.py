import pytest

from backend.valuation.dcf import (
    DCFAssumptions,
    InvalidAssumptionsError,
    build_default_scenarios,
    calculate_wacc,
    cost_of_equity_capm,
    run_dcf,
    run_scenarios,
    sensitivity_table,
)


def make_single_year_assumptions(**overrides) -> DCFAssumptions:
    """A 1-year forecast with round numbers, chosen so every intermediate
    figure can be verified by hand:

        base_revenue = 1000, growth = 10%  -> revenue = 1100
        EBIT = 1100 * 0.20 = 220
        NOPAT = 220 * (1 - 0.25) = 165
        D&A = 1100 * 0.05 = 55
        CapEx = 1100 * 0.06 = 66
        Change in NWC = (1100-1000) * 0.10 = 10
        FCF = 165 + 55 - 66 - 10 = 144

        Terminal FCF (yr2) = 144 * 1.02 = 146.88
        Terminal Value = 146.88 / (0.10 - 0.02) = 1836.0
        PV(TV) = 1836.0 / 1.10 = 1669.0909...
        PV(FCF1) = 144 / 1.10 = 130.90909...
        EV = 130.90909 + 1669.0909 = 1800.0
        Equity value = 1800 - 200 (net debt) = 1600
        Implied price = 1600 / 100 shares = 16.00
    """
    defaults = dict(
        base_revenue=1000.0,
        revenue_growth_rates=[0.10],
        ebit_margin=0.20,
        tax_rate=0.25,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.06,
        nwc_pct_revenue_change=0.10,
        wacc=0.10,
        terminal_growth=0.02,
        net_debt=200.0,
        shares_outstanding=100.0,
    )
    defaults.update(overrides)
    return DCFAssumptions(**defaults)


def test_single_year_fcf_matches_hand_calculation():
    result = run_dcf(make_single_year_assumptions())
    year1 = result.forecast[0]
    assert year1.revenue == pytest.approx(1100.0)
    assert year1.ebit == pytest.approx(220.0)
    assert year1.nopat == pytest.approx(165.0)
    assert year1.da == pytest.approx(55.0)
    assert year1.capex == pytest.approx(66.0)
    assert year1.nwc_change == pytest.approx(10.0)
    assert year1.fcf == pytest.approx(144.0)


def test_terminal_value_matches_hand_calculation():
    result = run_dcf(make_single_year_assumptions())
    assert result.terminal_value == pytest.approx(1836.0, rel=1e-6)


def test_enterprise_and_equity_value_match_hand_calculation():
    result = run_dcf(make_single_year_assumptions())
    assert result.enterprise_value == pytest.approx(1800.0, rel=1e-6)
    assert result.equity_value == pytest.approx(1600.0, rel=1e-6)


def test_implied_share_price_matches_hand_calculation():
    result = run_dcf(make_single_year_assumptions())
    assert result.implied_share_price == pytest.approx(16.00, rel=1e-6)


def test_multi_year_forecast_length():
    a = make_single_year_assumptions(revenue_growth_rates=[0.10, 0.08, 0.06, 0.05, 0.04])
    result = run_dcf(a)
    assert len(result.forecast) == 5
    # revenue compounds correctly year over year
    assert result.forecast[0].revenue == pytest.approx(1100.0)
    assert result.forecast[1].revenue == pytest.approx(1100.0 * 1.08)


def test_wacc_equal_to_terminal_growth_raises():
    a = make_single_year_assumptions(wacc=0.05, terminal_growth=0.05)
    with pytest.raises(InvalidAssumptionsError):
        run_dcf(a)


def test_wacc_less_than_terminal_growth_raises():
    a = make_single_year_assumptions(wacc=0.03, terminal_growth=0.05)
    with pytest.raises(InvalidAssumptionsError):
        run_dcf(a)


def test_missing_growth_rates_raises():
    a = make_single_year_assumptions(revenue_growth_rates=[])
    with pytest.raises(InvalidAssumptionsError):
        run_dcf(a)


def test_negative_shares_outstanding_raises():
    a = make_single_year_assumptions(shares_outstanding=-10)
    with pytest.raises(InvalidAssumptionsError):
        run_dcf(a)


def test_tax_rate_out_of_bounds_raises():
    a = make_single_year_assumptions(tax_rate=1.5)
    with pytest.raises(InvalidAssumptionsError):
        run_dcf(a)


def test_scenarios_produce_bear_lt_base_lt_bull():
    base = make_single_year_assumptions(revenue_growth_rates=[0.10, 0.08, 0.06])
    scenarios = build_default_scenarios(base)
    results = run_scenarios(scenarios)
    assert results["bear"].implied_share_price < results["base"].implied_share_price
    assert results["base"].implied_share_price < results["bull"].implied_share_price


def test_sensitivity_table_shape_and_diagonal_values():
    base = make_single_year_assumptions()
    table = sensitivity_table(base, wacc_range=[0.08, 0.10, 0.12], terminal_growth_range=[0.01, 0.02])
    assert len(table["prices"]) == 3
    assert all(len(row) == 2 for row in table["prices"])
    # the [wacc=0.10, growth=0.02] cell should match the base-case price exactly
    idx_wacc = table["wacc_values"].index(0.10)
    idx_growth = table["growth_values"].index(0.02)
    assert table["prices"][idx_wacc][idx_growth] == pytest.approx(16.00, rel=1e-6)


def test_sensitivity_table_marks_undefined_cells_none():
    base = make_single_year_assumptions()
    table = sensitivity_table(base, wacc_range=[0.02], terminal_growth_range=[0.05])
    assert table["prices"][0][0] is None  # wacc <= terminal_growth


def test_wacc_calculation():
    # E=800, D=200, Re=12%, Rd=5%, tax=25%
    # weights: E=0.8, D=0.2
    # WACC = 0.8*0.12 + 0.2*0.05*0.75 = 0.096 + 0.0075 = 0.1035
    w = calculate_wacc(market_cap=800, total_debt=200, cost_of_equity=0.12, cost_of_debt=0.05, tax_rate=0.25)
    assert w == pytest.approx(0.1035)


def test_capm_cost_of_equity():
    # Re = 4% + 1.2 * 5.5% = 4% + 6.6% = 10.6%
    re = cost_of_equity_capm(risk_free_rate=0.04, beta=1.2, equity_risk_premium=0.055)
    assert re == pytest.approx(0.106)
