# Financial Model Methodology

This document defines exactly how every metric in EquityLens is calculated.
Formulas match `backend/financial_engine/ratios.py`,
`backend/valuation/dcf.py`, and `backend/valuation/comparables.py` line for
line — if the code and this doc ever disagree, the code's unit tests
(`tests/test_ratios.py`, `tests/test_dcf.py`, `tests/test_comparables.py`)
are the tiebreaker.

## Ratios

| Ratio | Formula |
|---|---|
| Revenue growth | (Revenue_t − Revenue_t-1) / Revenue_t-1 |
| Gross margin | Gross Profit / Revenue |
| Operating margin | EBIT / Revenue |
| Net margin | Net Income / Revenue |
| EBITDA margin | EBITDA / Revenue, where EBITDA = EBIT + D&A |
| EPS growth | (EPS_t − EPS_t-1) / \|EPS_t-1\| |
| Free cash flow | Reported FCF if available, else Operating Cash Flow − CapEx |
| FCF margin | Free Cash Flow / Revenue |
| ROE | Net Income / Total Equity |
| ROIC | NOPAT / Invested Capital, where NOPAT = EBIT × (1 − effective tax rate) and Invested Capital = Total Debt + Total Equity − Cash |
| Debt/Equity | Total Debt / Total Equity |
| Net Debt/EBITDA | (Total Debt − Cash) / EBITDA |
| Current ratio | Total Current Assets / Total Current Liabilities |

Every ratio function returns `None` (not zero, not an exception) when a
required line item is missing or a denominator is zero — the API and report
generator render this as `"n/a"` rather than a misleading `0.0` or `0%`.

## DCF Valuation

**Per forecast year t:**
```
Revenue_t   = Revenue_(t-1) x (1 + growth_rate_t)
EBIT_t      = Revenue_t x EBIT margin
NOPAT_t     = EBIT_t x (1 − tax rate)
D&A_t       = Revenue_t x D&A % of revenue
CapEx_t     = Revenue_t x CapEx % of revenue
ΔNWC_t      = (Revenue_t − Revenue_(t-1)) x NWC % of revenue change
FCF_t       = NOPAT_t + D&A_t − CapEx_t − ΔNWC_t
PV(FCF_t)   = FCF_t / (1 + WACC)^t
```

**Terminal value** (Gordon Growth, applied after the final forecast year n):
```
Terminal FCF_(n+1) = FCF_n x (1 + terminal growth)
Terminal Value      = Terminal FCF_(n+1) / (WACC − terminal growth)
PV(Terminal Value)  = Terminal Value / (1 + WACC)^n
```

**Bridge to equity value:**
```
Enterprise Value = Σ PV(FCF_1..n) + PV(Terminal Value)
Equity Value     = Enterprise Value − Net Debt        [Net Debt = Total Debt − Cash]
Implied Price    = Equity Value / Diluted Shares Outstanding
```

### Validation (enforced before any calculation runs)

- `WACC` must be **strictly greater than** terminal growth — otherwise the
  terminal-value denominator is zero or negative, which is mathematically
  undefined, not just "a bad estimate." The engine raises
  `InvalidAssumptionsError` rather than returning a nonsensical number.
- At least one forecast-year growth rate is required.
- `base_revenue` and `shares_outstanding` must be positive.
- `tax_rate` must be between 0 and 1; `ebit_margin` between −100% and 100%.

### WACC

```
WACC = E/(D+E) x Re  +  D/(D+E) x Rd x (1 − Tax Rate)
```
where `Re` (cost of equity) is typically computed via CAPM:
```
Re = Risk-free rate + Beta x Equity Risk Premium
```
Both helpers are in `backend/valuation/dcf.py`
(`calculate_wacc`, `cost_of_equity_capm`) but the `/dcf` endpoint currently
takes WACC as a direct input — wiring a `/wacc` endpoint that derives it
from live beta/risk-free-rate data is a suggested next improvement (see README).

## Scenario analysis (bear / base / bull)

`build_default_scenarios()` derives bear/bull cases from a base case by:
- Scaling every forecast-year revenue growth rate by `(1 ± spread)` (default spread: 30% relative)
- Flexing EBIT margin by ∓/± 3 percentage points
- Flexing WACC by ±/∓ 100 basis points
- Flexing terminal growth by ∓/± 50 basis points

This is a convenience default, not a substitute for analyst judgment — real
scenario analysis should author explicit, independently-justified
assumptions per scenario (the `ScenarioSet` dataclass accepts any three
`DCFAssumptions` objects, not just derived ones).

## Sensitivity table

A 2D grid: rows = WACC values, columns = terminal growth values, cells =
implied share price holding every other assumption at the base case. Cells
where `WACC ≤ terminal growth` are explicitly `None` (undefined), never a
computed-but-meaningless number.

## Comparable company analysis

**Per peer:**
```
Market Cap        = Price x Shares Outstanding
Enterprise Value   = Market Cap + Total Debt − Cash
P/E                = Market Cap / Net Income
EV/EBITDA          = Enterprise Value / EBITDA
EV/Revenue         = Enterprise Value / Revenue
Price/Sales        = Market Cap / Revenue
FCF Yield          = Free Cash Flow / Market Cap
```

**Implied valuation for the subject company:**
```
Implied Equity Value (from P/E)       = median peer P/E x subject Net Income
Implied Enterprise Value (from EV/X)  = median peer EV/X x subject metric X
Implied Equity Value (from EV/X)      = Implied EV − subject Net Debt
Implied Price                          = Implied Equity Value / subject Shares Outstanding
```

**Median vs. mean:** the median is used as the primary multiple because a
single outlier peer (e.g. one trading at a distressed or hyped multiple)
distorts a mean far more than a median. Both are reported so the reader can
judge dispersion themselves.

## Portfolio analytics

| Metric | Formula |
|---|---|
| Total return | (P_end / P_start) − 1 |
| Annualized return | (P_end / P_start)^(periods_per_year / n_periods) − 1 |
| Volatility | Sample stdev of periodic returns, annualized by × √(periods_per_year) |
| Sharpe ratio | (Annualized mean return − risk-free rate) / Annualized volatility |
| Max drawdown | min over t of (Price_t − running max up to t) / running max up to t |
| Beta | Cov(asset returns, benchmark returns) / Var(benchmark returns) |
| Correlation matrix | Pearson correlation of periodic returns across assets |

`periods_per_year` defaults to 252 (daily trading days). Feed the functions
weekly or monthly prices and pass the matching `periods_per_year` (52 or
12) — the default assumes daily data.
