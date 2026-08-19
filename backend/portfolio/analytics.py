"""
Portfolio analytics engine.

All functions take plain lists/arrays of periodic returns (or prices) so
they're independent of the DB/ORM and trivially unit-testable against
hand-computed values.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def prices_to_returns(prices: list[float]) -> list[float]:
    """Simple (not log) period-over-period returns."""
    return [(prices[i] / prices[i - 1]) - 1 for i in range(1, len(prices))]


def total_return(prices: list[float]) -> float:
    if len(prices) < 2 or prices[0] == 0:
        raise ValueError("Need at least 2 non-zero price points.")
    return (prices[-1] / prices[0]) - 1


def annualized_return(prices: list[float], periods_per_year: int = 252) -> float:
    if len(prices) < 2 or prices[0] <= 0:
        raise ValueError("Need at least 2 positive price points.")
    n_periods = len(prices) - 1
    cumulative = prices[-1] / prices[0]
    years = n_periods / periods_per_year
    if years <= 0:
        raise ValueError("Need a positive time span to annualize.")
    return cumulative ** (1 / years) - 1


def volatility(returns: list[float], periods_per_year: int = 252, annualize: bool = True) -> float:
    if len(returns) < 2:
        raise ValueError("Need at least 2 return observations.")
    arr = np.array(returns, dtype=float)
    vol = float(np.std(arr, ddof=1))
    return vol * np.sqrt(periods_per_year) if annualize else vol


def sharpe_ratio(
    returns: list[float],
    risk_free_rate_annual: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Sharpe = (annualized mean return - risk-free rate) / annualized volatility."""
    if len(returns) < 2:
        raise ValueError("Need at least 2 return observations.")
    arr = np.array(returns, dtype=float)
    mean_period_return = float(np.mean(arr))
    annualized_mean_return = (1 + mean_period_return) ** periods_per_year - 1
    ann_vol = volatility(returns, periods_per_year, annualize=True)
    if ann_vol == 0:
        raise ValueError("Volatility is zero; Sharpe ratio is undefined.")
    return (annualized_mean_return - risk_free_rate_annual) / ann_vol


@dataclass
class DrawdownResult:
    max_drawdown: float          # negative number, e.g. -0.23 for -23%
    peak_index: int
    trough_index: int
    drawdown_series: list[float]  # drawdown at each point, <= 0


def max_drawdown(prices: list[float]) -> DrawdownResult:
    if len(prices) < 2:
        raise ValueError("Need at least 2 price points.")
    arr = np.array(prices, dtype=float)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    trough_idx = int(np.argmin(drawdowns))
    # peak is the running max index up to the trough
    peak_idx = int(np.argmax(arr[: trough_idx + 1]))
    return DrawdownResult(
        max_drawdown=float(drawdowns[trough_idx]),
        peak_index=peak_idx,
        trough_index=trough_idx,
        drawdown_series=drawdowns.tolist(),
    )


def beta(asset_returns: list[float], benchmark_returns: list[float]) -> float:
    """Beta = Cov(asset, benchmark) / Var(benchmark)."""
    if len(asset_returns) != len(benchmark_returns):
        raise ValueError("asset_returns and benchmark_returns must be the same length.")
    if len(asset_returns) < 2:
        raise ValueError("Need at least 2 return observations.")
    a = np.array(asset_returns, dtype=float)
    b = np.array(benchmark_returns, dtype=float)
    cov_matrix = np.cov(a, b, ddof=1)
    benchmark_var = cov_matrix[1, 1]
    if benchmark_var == 0:
        raise ValueError("Benchmark variance is zero; beta is undefined.")
    return float(cov_matrix[0, 1] / benchmark_var)


def correlation_matrix(returns_by_asset: dict[str, list[float]]) -> dict:
    """Returns {"tickers": [...], "matrix": [[...], ...]} — a JSON-friendly
    correlation matrix in ticker order."""
    tickers = list(returns_by_asset.keys())
    lengths = {len(v) for v in returns_by_asset.values()}
    if len(lengths) != 1:
        raise ValueError("All assets must have the same number of return observations.")
    data = np.array([returns_by_asset[t] for t in tickers])
    corr = np.corrcoef(data)
    return {"tickers": tickers, "matrix": corr.tolist()}


def position_weights(position_values: dict[str, float]) -> dict[str, float]:
    total = sum(position_values.values())
    if total <= 0:
        raise ValueError("Total portfolio value must be positive.")
    return {ticker: value / total for ticker, value in position_values.items()}
