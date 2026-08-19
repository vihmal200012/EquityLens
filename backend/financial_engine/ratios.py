"""
Financial ratio engine.

Pure functions: raw statement dicts in, ratios out. No I/O, no DB, no
network — this is what makes it trivially unit-testable. All statement
dicts use the line-item keys produced by providers/mock_provider.py and
providers/live_provider.py (see StatementPeriod.data).

Every function returns `None` instead of raising when a required line
item is missing or a denominator is zero/undefined, so callers can render
"n/a" rather than crashing or, worse, showing a wrong number.
"""
from __future__ import annotations

from dataclasses import dataclass


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


@dataclass
class YearFinancials:
    """One fiscal year's worth of statement data, bundled for ratio calcs."""

    fiscal_year: int
    income: dict
    balance: dict
    cash_flow: dict


def revenue_growth(current: YearFinancials, prior: YearFinancials | None) -> float | None:
    if prior is None:
        return None
    return _safe_div(
        current.income.get("revenue", 0) - prior.income.get("revenue", 0),
        prior.income.get("revenue"),
    )


def gross_margin(year: YearFinancials) -> float | None:
    return _safe_div(year.income.get("gross_profit"), year.income.get("revenue"))


def operating_margin(year: YearFinancials) -> float | None:
    return _safe_div(year.income.get("ebit"), year.income.get("revenue"))


def net_margin(year: YearFinancials) -> float | None:
    return _safe_div(year.income.get("net_income"), year.income.get("revenue"))


def ebitda_margin(year: YearFinancials) -> float | None:
    return _safe_div(year.income.get("ebitda"), year.income.get("revenue"))


def eps_growth(current: YearFinancials, prior: YearFinancials | None) -> float | None:
    if prior is None:
        return None
    cur_eps = current.income.get("eps")
    prior_eps = prior.income.get("eps")
    if cur_eps is None or prior_eps is None or prior_eps == 0:
        return None
    return (cur_eps - prior_eps) / abs(prior_eps)


def free_cash_flow(year: YearFinancials) -> float | None:
    fcf = year.cash_flow.get("free_cash_flow")
    if fcf is not None:
        return fcf
    ocf = year.cash_flow.get("operating_cash_flow")
    capex = year.cash_flow.get("capital_expenditures")
    if ocf is None or capex is None:
        return None
    return ocf - capex


def fcf_margin(year: YearFinancials) -> float | None:
    fcf = free_cash_flow(year)
    return _safe_div(fcf, year.income.get("revenue"))


def roe(year: YearFinancials) -> float | None:
    """Return on equity = Net income / Total equity."""
    return _safe_div(year.income.get("net_income"), year.balance.get("total_equity"))


def roic(year: YearFinancials) -> float | None:
    """Return on invested capital = NOPAT / Invested capital, where
    NOPAT = EBIT x (1 - effective tax rate) and
    Invested capital = Total debt + Total equity - Cash."""
    ebit = year.income.get("ebit")
    pretax = year.income.get("pretax_income")
    tax = year.income.get("tax_expense")
    if ebit is None:
        return None
    effective_tax_rate = _safe_div(tax, pretax) if pretax not in (None, 0) else 0.0
    effective_tax_rate = effective_tax_rate if effective_tax_rate is not None else 0.0
    nopat = ebit * (1 - effective_tax_rate)

    debt = year.balance.get("total_debt")
    equity = year.balance.get("total_equity")
    cash = year.balance.get("cash_and_equivalents")
    if debt is None or equity is None or cash is None:
        return None
    invested_capital = debt + equity - cash
    return _safe_div(nopat, invested_capital)


def debt_to_equity(year: YearFinancials) -> float | None:
    return _safe_div(year.balance.get("total_debt"), year.balance.get("total_equity"))


def net_debt_to_ebitda(year: YearFinancials) -> float | None:
    debt = year.balance.get("total_debt")
    cash = year.balance.get("cash_and_equivalents")
    ebitda = year.income.get("ebitda")
    if debt is None or cash is None:
        return None
    net_debt = debt - cash
    return _safe_div(net_debt, ebitda)


def current_ratio(year: YearFinancials) -> float | None:
    return _safe_div(year.balance.get("total_current_assets"), year.balance.get("total_current_liabilities"))


RATIO_FUNCS = {
    "gross_margin": gross_margin,
    "operating_margin": operating_margin,
    "net_margin": net_margin,
    "ebitda_margin": ebitda_margin,
    "free_cash_flow": free_cash_flow,
    "fcf_margin": fcf_margin,
    "roe": roe,
    "roic": roic,
    "debt_to_equity": debt_to_equity,
    "net_debt_to_ebitda": net_debt_to_ebitda,
    "current_ratio": current_ratio,
}

GROWTH_FUNCS = {
    "revenue_growth": revenue_growth,
    "eps_growth": eps_growth,
}


def compute_ratio_set(year: YearFinancials, prior: YearFinancials | None) -> dict:
    """Compute the full named ratio bundle for one fiscal year, given the
    prior year for growth calcs (pass prior=None for the earliest year)."""
    result = {name: fn(year) for name, fn in RATIO_FUNCS.items()}
    result.update({name: fn(year, prior) for name, fn in GROWTH_FUNCS.items()})
    return result


def compute_ratio_series(years: list[YearFinancials]) -> dict[int, dict]:
    """years must be sorted ascending (oldest first). Returns
    {fiscal_year: ratio_dict}."""
    out = {}
    for i, year in enumerate(years):
        prior = years[i - 1] if i > 0 else None
        out[year.fiscal_year] = compute_ratio_set(year, prior)
    return out
