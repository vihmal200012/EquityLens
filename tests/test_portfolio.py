import pytest

from backend.portfolio.analytics import (
    annualized_return,
    beta,
    correlation_matrix,
    max_drawdown,
    position_weights,
    prices_to_returns,
    sharpe_ratio,
    total_return,
    volatility,
)


def test_prices_to_returns():
    prices = [100, 110, 99]
    returns = prices_to_returns(prices)
    assert returns[0] == pytest.approx(0.10)
    assert returns[1] == pytest.approx(-0.10)


def test_total_return():
    assert total_return([100, 150]) == pytest.approx(0.5)


def test_annualized_return_one_year_252_periods():
    # doubling over exactly 252 periods (1 year) = 100% annualized
    prices = [100.0] + [100.0] * 251 + [200.0]
    assert annualized_return(prices, periods_per_year=252) == pytest.approx(1.0, rel=1e-6)


def test_volatility_known_series():
    # returns with sample stdev computable by hand
    returns = [0.01, -0.01, 0.02, -0.02, 0.0]
    import numpy as np
    expected_daily = float(np.std(np.array(returns), ddof=1))
    result = volatility(returns, periods_per_year=1, annualize=False)
    assert result == pytest.approx(expected_daily)


def test_sharpe_ratio_zero_vol_raises():
    # a constant return series has zero sample stdev -> Sharpe is undefined
    with pytest.raises(ValueError):
        sharpe_ratio([0.001] * 5, periods_per_year=1)


def test_sharpe_ratio_positive_for_positive_excess_return():
    returns = [0.002, 0.001, 0.003, -0.001, 0.0025, 0.0015]
    s = sharpe_ratio(returns, risk_free_rate_annual=0.0, periods_per_year=252)
    assert s > 0


def test_max_drawdown_simple_series():
    # prices: 100 -> 120 (peak) -> 90 (trough) -> 110
    prices = [100, 120, 90, 110]
    result = max_drawdown(prices)
    # drawdown at trough = (90-120)/120 = -0.25
    assert result.max_drawdown == pytest.approx(-0.25)
    assert result.peak_index == 1
    assert result.trough_index == 2


def test_beta_identical_series_is_one():
    returns = [0.01, -0.02, 0.03, 0.0, -0.01]
    assert beta(returns, returns) == pytest.approx(1.0)


def test_beta_double_volatility_series_is_two():
    benchmark = [0.01, -0.02, 0.03, 0.0, -0.01]
    asset = [r * 2 for r in benchmark]
    assert beta(asset, benchmark) == pytest.approx(2.0)


def test_correlation_matrix_self_correlation_is_one():
    data = {
        "A": [0.01, 0.02, -0.01, 0.03],
        "B": [0.02, 0.01, -0.02, 0.01],
    }
    result = correlation_matrix(data)
    assert result["matrix"][0][0] == pytest.approx(1.0)
    assert result["matrix"][1][1] == pytest.approx(1.0)


def test_position_weights_sum_to_one():
    weights = position_weights({"AAPL": 500, "MSFT": 300, "NVDA": 200})
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["AAPL"] == pytest.approx(0.5)


def test_position_weights_zero_total_raises():
    with pytest.raises(ValueError):
        position_weights({"AAPL": 0, "MSFT": 0})
