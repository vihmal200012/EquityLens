# Data Sources

## DEMO MODE (default, no API key required)

`backend/providers/mock_provider.py` generates synthetic financial
statements for three tickers: **AAPL, MSFT, NVDA**.

**How the synthetic data is built:** each ticker has a hand-set "base year"
profile (revenue scale, gross margin, opex %, D&A %, CapEx %, tax rate,
cash, debt — loosely calibrated to the real company's approximate size and
margin profile for realism) in `_PROFILES`. `_synthesize_years()` then walks
backwards from that base year, applying a decaying growth rate, to produce
5 years of **internally consistent** statements: the balance sheet balances,
cash flow ties to net income + D&A − ΔNWC − CapEx, EBITDA = EBIT + D&A, etc.

**This is not real financial data.** It's structured to be realistic enough
to exercise every part of the financial engine (ratios that make sense,
margins in a believable range, a DCF that produces a plausible-if-wrong
price), but it is explicitly not sourced from any company's actual SEC
filings or investor relations materials. Every record `MockProvider`
produces is tagged `source: "demo"`:
- In the database (`DataSource.DEMO` on `Company`, `FinancialStatement`, `MarketData`)
- In every API response (`"data_mode": "demo"`)
- In the AI assistant's context (`data_mode` field, with an explicit
  instruction to disclose it before answering quantitative questions)
- In the generated research report (a `⚠ DEMO MODE` banner prepended to every
  numeric section)

## Live data (optional)

Set `FINANCIAL_API_KEY` to activate `backend/providers/live_provider.py`,
an adapter built against a Financial-Modeling-Prep-style REST API
(`profile/{ticker}`, `income-statement/{ticker}`,
`balance-sheet-statement/{ticker}`, `cash-flow-statement/{ticker}`,
`quote/{ticker}`). If you have a key for a different provider (Alpha
Vantage, IEX, Polygon, etc.), write a new class implementing
`FinancialDataProvider` (see `backend/providers/base.py`) with that
provider's actual endpoint shapes — the rest of the app doesn't change.

Vendor payloads come back in that API's own field names and sign
conventions (e.g. `totalDebt`, `operatingIncome`, capex reported as a
negative outflow). `LiveProvider` maps every statement it returns onto the
same internal snake_case schema `MockProvider` produces (`total_debt`,
`ebit`, capex as a positive magnitude, etc.) before handing it to
`ratios.py` / `dcf.py` — see the field-map tables at the top of
`backend/providers/live_provider.py`. `shares_outstanding` isn't present on
FMP's balance-sheet endpoint at all; `LiveProvider` fetches it from the
profile endpoint once per ticker and attaches it to each balance-sheet
year.

Two layers of fallback exist, and they mean different things:
- **At startup**, `get_provider()` uses `LiveProvider` only if
  `FINANCIAL_API_KEY` is set *and* constructing it succeeds (i.e. a key
  string is present) — otherwise it falls back to `MockProvider` for the
  whole process, logged.
- **Per request**, if the resolved provider is live and an individual call
  fails later (bad key, network error, rate limit), the API layer
  (`backend/api/main.py`'s `_with_live_fallback`) retries that one request
  against demo data rather than crashing or returning a partial/wrong
  result. This fallback is logged, never silent, and the response's
  `data_mode` field says `"demo"` for that request even though a live key
  is configured — so the client always knows which data it actually got,
  never a live key silently paired with stale/wrong demo numbers labeled
  as live.

## What is never done

- Static demo numbers are never presented as live data (`data_mode` is on
  every relevant response and DB row).
- The app never falls back to inventing numbers when a provider call fails
  — it either serves demo data (explicitly labeled) or returns an error.
- The AI assistant never fetches its own data from the open web; it only
  sees the structured context assembled from the same provider/DB layer
  everything else uses (see `docs/AI_DESIGN.md`).
