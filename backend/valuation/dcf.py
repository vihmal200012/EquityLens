"""
Discounted Cash Flow valuation engine.

    FCF_t = EBIT_t x (1 - tax_rate)
            + D&A_t
            - CapEx_t
            - Change in NWC_t

    PV of FCF_t = FCF_t / (1 + WACC)^t

    Terminal Value (at year n, Gordon Growth) =
        FCF_(n+1) / (WACC - terminal_growth)
      = FCF_n x (1 + terminal_growth) / (WACC - terminal_growth)

    PV of Terminal Value = Terminal Value / (1 + WACC)^n

    Enterprise Value = sum(PV of FCF_1..n) + PV of Terminal Value
    Equity Value     = Enterprise Value - Net Debt  (Net Debt = Total Debt - Cash)
    Implied Price    = Equity Value / Diluted Shares Outstanding

This module performs no I/O — it's pure math over a DCFAssumptions object,
which is what makes it unit-testable against hand-computed expected values.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class InvalidAssumptionsError(ValueError):
    """Raised when DCF inputs are missing or would produce a
    mathematically meaningless/undefined result (e.g. WACC <= terminal
    growth, which makes the terminal-value denominator zero or negative)."""


@dataclass
class DCFAssumptions:
    base_revenue: float                 # most recent actual/trailing revenue
    revenue_growth_rates: list[float]    # one rate per forecast year, e.g. 5 years
    ebit_margin: float                   # assumed EBIT margin, applied to each forecast year's revenue
    tax_rate: float
    da_pct_revenue: float                # D&A as % of revenue
    capex_pct_revenue: float             # CapEx as % of revenue
    nwc_pct_revenue_change: float        # change in NWC as % of the *change* in revenue
    wacc: float
    terminal_growth: float
    net_debt: float                      # total debt - cash & equivalents
    shares_outstanding: float

    def validate(self) -> None:
        errors = []
        if not self.revenue_growth_rates:
            errors.append("At least one forecast-year revenue growth rate is required.")
        if self.base_revenue is None or self.base_revenue <= 0:
            errors.append("base_revenue must be a positive number.")
        if self.shares_outstanding is None or self.shares_outstanding <= 0:
            errors.append("shares_outstanding must be a positive number.")
        if self.wacc is None:
            errors.append("wacc is required.")
        if self.terminal_growth is None:
            errors.append("terminal_growth is required.")
        if self.wacc is not None and self.terminal_growth is not None and self.wacc <= self.terminal_growth:
            errors.append(
                f"WACC ({self.wacc:.2%}) must be strictly greater than terminal growth "
                f"({self.terminal_growth:.2%}) — otherwise the Gordon Growth terminal value "
                "denominator is zero or negative and the model is undefined."
            )
        if self.tax_rate is not None and not (0 <= self.tax_rate <= 1):
            errors.append("tax_rate must be between 0 and 1.")
        if self.ebit_margin is not None and not (-1 <= self.ebit_margin <= 1):
            errors.append("ebit_margin must be between -100% and 100%.")
        if errors:
            raise InvalidAssumptionsError("; ".join(errors))


@dataclass
class ForecastYear:
    year_index: int  # 1..n
    revenue: float
    ebit: float
    nopat: float
    da: float
    capex: float
    nwc_change: float
    fcf: float
    discount_factor: float
    pv_fcf: float


@dataclass
class DCFResult:
    forecast: list[ForecastYear]
    terminal_value: float
    pv_terminal_value: float
    sum_pv_fcf: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float
    assumptions: DCFAssumptions = field(repr=False)


def run_dcf(assumptions: DCFAssumptions) -> DCFResult:
    a = assumptions
    a.validate()

    forecast: list[ForecastYear] = []
    revenue = a.base_revenue
    prior_revenue = a.base_revenue

    for i, g in enumerate(a.revenue_growth_rates, start=1):
        revenue = revenue * (1 + g)
        ebit = revenue * a.ebit_margin
        nopat = ebit * (1 - a.tax_rate)
        da = revenue * a.da_pct_revenue
        capex = revenue * a.capex_pct_revenue
        nwc_change = (revenue - prior_revenue) * a.nwc_pct_revenue_change
        fcf = nopat + da - capex - nwc_change
        discount_factor = 1 / ((1 + a.wacc) ** i)
        pv_fcf = fcf * discount_factor

        forecast.append(
            ForecastYear(
                year_index=i,
                revenue=revenue,
                ebit=ebit,
                nopat=nopat,
                da=da,
                capex=capex,
                nwc_change=nwc_change,
                fcf=fcf,
                discount_factor=discount_factor,
                pv_fcf=pv_fcf,
            )
        )
        prior_revenue = revenue

    n = len(forecast)
    terminal_fcf_next_year = forecast[-1].fcf * (1 + a.terminal_growth)
    terminal_value = terminal_fcf_next_year / (a.wacc - a.terminal_growth)
    pv_terminal_value = terminal_value / ((1 + a.wacc) ** n)

    sum_pv_fcf = sum(f.pv_fcf for f in forecast)
    enterprise_value = sum_pv_fcf + pv_terminal_value
    equity_value = enterprise_value - a.net_debt
    implied_share_price = equity_value / a.shares_outstanding

    return DCFResult(
        forecast=forecast,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        sum_pv_fcf=sum_pv_fcf,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        implied_share_price=implied_share_price,
        assumptions=a,
    )


# ---------------------------------------------------------------------------
# Scenario analysis (bear / base / bull)
# ---------------------------------------------------------------------------

@dataclass
class ScenarioSet:
    bear: DCFAssumptions
    base: DCFAssumptions
    bull: DCFAssumptions


def run_scenarios(scenarios: ScenarioSet) -> dict[str, DCFResult]:
    return {
        "bear": run_dcf(scenarios.bear),
        "base": run_dcf(scenarios.base),
        "bull": run_dcf(scenarios.bull),
    }


def build_default_scenarios(base: DCFAssumptions, spread: float = 0.30) -> ScenarioSet:
    """Convenience helper: derive bear/bull cases from a base case by
    flexing revenue growth +/- `spread` (relative) and WACC/terminal growth
    by +/- 100bps, holding everything else constant. Callers doing real
    analysis should still author explicit assumptions per scenario."""
    def scale_growth(rates: list[float], factor: float) -> list[float]:
        return [r * factor for r in rates]

    bear = DCFAssumptions(
        **{
            **base.__dict__,
            "revenue_growth_rates": scale_growth(base.revenue_growth_rates, 1 - spread),
            "ebit_margin": max(base.ebit_margin - 0.03, 0.0),
            "wacc": base.wacc + 0.01,
            "terminal_growth": max(base.terminal_growth - 0.005, 0.0),
        }
    )
    bull = DCFAssumptions(
        **{
            **base.__dict__,
            "revenue_growth_rates": scale_growth(base.revenue_growth_rates, 1 + spread),
            "ebit_margin": base.ebit_margin + 0.03,
            "wacc": max(base.wacc - 0.01, base.terminal_growth + 0.005),
            "terminal_growth": base.terminal_growth + 0.005,
        }
    )
    return ScenarioSet(bear=bear, base=base, bull=bull)


# ---------------------------------------------------------------------------
# Two-variable sensitivity table (WACC rows x terminal growth columns)
# ---------------------------------------------------------------------------

def sensitivity_table(
    base: DCFAssumptions,
    wacc_range: list[float],
    terminal_growth_range: list[float],
) -> dict:
    """Returns {"wacc_values": [...], "growth_values": [...],
    "prices": [[price for each growth] for each wacc]}. Cells where
    wacc <= terminal_growth are None (undefined), not silently skipped."""
    rows = []
    for w in wacc_range:
        row = []
        for tg in terminal_growth_range:
            if w <= tg:
                row.append(None)
                continue
            trial = DCFAssumptions(**{**base.__dict__, "wacc": w, "terminal_growth": tg})
            try:
                result = run_dcf(trial)
                row.append(round(result.implied_share_price, 2))
            except InvalidAssumptionsError:
                row.append(None)
        rows.append(row)
    return {
        "wacc_values": wacc_range,
        "growth_values": terminal_growth_range,
        "prices": rows,
    }


# ---------------------------------------------------------------------------
# WACC helper (CAPM cost of equity + after-tax cost of debt, weighted)
# ---------------------------------------------------------------------------

def calculate_wacc(
    market_cap: float,
    total_debt: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float:
    """WACC = E/(D+E) x Re + D/(D+E) x Rd x (1 - Tax Rate)"""
    total_capital = market_cap + total_debt
    if total_capital <= 0:
        raise InvalidAssumptionsError("market_cap + total_debt must be positive to compute WACC.")
    e_weight = market_cap / total_capital
    d_weight = total_debt / total_capital
    return e_weight * cost_of_equity + d_weight * cost_of_debt * (1 - tax_rate)


def cost_of_equity_capm(risk_free_rate: float, beta: float, equity_risk_premium: float) -> float:
    """Re = Rf + Beta x Equity Risk Premium"""
    return risk_free_rate + beta * equity_risk_premium
