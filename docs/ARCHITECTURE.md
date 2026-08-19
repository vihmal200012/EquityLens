# Architecture

## Layering

```
┌─────────────────────────────────────────────┐
│  API (backend/api/main.py)                    │  FastAPI routes: validation,
│                                                │  HTTP status codes, wiring
├─────────────────────────────────────────────┤
│  Engines (financial_engine / valuation /      │  Pure functions.
│  portfolio / reports)                         │  No I/O. No DB. No network.
├─────────────────────────────────────────────┤
│  Providers (providers/base.py + adapters)     │  The ONLY place that talks
│                                                │  to an external data source.
├─────────────────────────────────────────────┤
│  Database (database/models.py + session.py)   │  SQLAlchemy ORM, 9 tables.
└─────────────────────────────────────────────┘
```

The rule enforced throughout: **calculations never live in a route handler,
and route handlers never compute finance themselves** — they call into
`financial_engine`, `valuation`, or `portfolio`, all of which are pure
functions over plain Python dataclasses. This is what makes 57 of the 75
tests runnable with zero mocking, zero DB, zero network — they call the
function, pass in fixture data, assert the output.

## Provider abstraction

```
FinancialDataProvider (abstract base, providers/base.py)
    ├── MockProvider     — DEMO MODE, synthetic data, zero setup
    └── LiveProvider     — real REST API adapter, requires FINANCIAL_API_KEY
```

`get_provider()` in `providers/live_provider.py` resolves which one to use
at app startup: `LiveProvider` if `FINANCIAL_API_KEY` is set, `MockProvider`
otherwise — logged either way, never silent. This startup check only
confirms a key string is configured, not that the vendor API is actually
reachable; if a live request fails later (bad key, network error, rate
limit), `backend/api/main.py`'s `_with_live_fallback` retries that one
request against demo data and labels the response `data_mode: "demo"`
accordingly (see `docs/DATA_SOURCES.md`) rather than crashing or silently
presenting stale/demo numbers as live. Every consumer of provider data (the
ratio engine, the DCF endpoint, the AI context builder) only ever sees the
`FinancialDataProvider` interface, so adding a second real provider (e.g.
Alpha Vantage alongside FMP) means writing one new adapter class and
nothing else changes.

## Database schema

Nine tables, matching the spec exactly:

| Table | Purpose |
|---|---|
| `companies` | Ticker, name, sector, shares outstanding, provenance |
| `financial_statements` | Income/balance/cash-flow line items as JSON, keyed by (company, type, fiscal year) |
| `market_data` | Daily price/market cap/EV snapshots |
| `ratios` | Computed ratio bundles per fiscal year (always `source=calculated`) |
| `valuations` | A versioned valuation run (DCF or comps), `results` JSON |
| `valuation_assumptions` | One row per scenario (bear/base/bull) per valuation |
| `portfolio_positions` | User-entered portfolio holdings |
| `portfolio_snapshots` | Daily portfolio value, for return/vol/drawdown calcs |
| `research_reports` | Generated report sections, flagged `ai_assisted` |

Every table that represents a fact carries a `source` enum
(`demo` / `live_api` / `user_input` / `calculated`) and a timestamp, so the
app can always answer "where did this number come from and when."
Financial statement line items are stored as JSON rather than one column
per line item — this means adding a new line item a provider returns
doesn't require a migration, and the ratio engine reads keys defensively
(`dict.get(...)`, returns `None` rather than raising on a missing key).

## Request flow example: running a DCF

1. Client `POST /api/companies/AAPL/dcf` with assumptions.
2. Route handler loads the latest fiscal year via the resolved provider
   (`_load_years`), pulls `total_debt`, `cash`, and `shares_outstanding`
   from the balance sheet to compute net debt.
3. Handler builds a `DCFAssumptions` dataclass and calls `run_dcf()` — pure
   function, no I/O.
4. `run_dcf()` calls `.validate()` first (raises `InvalidAssumptionsError`
   on e.g. WACC ≤ terminal growth), then does the FCF build-up, discounting,
   and terminal value math.
5. Handler catches `InvalidAssumptionsError` and returns HTTP 422 with the
   specific reason; otherwise serializes `DCFResult` to JSON.

## Why pure-function engines matter here

The spec's Section 7 ("Financial Correctness") requires the DCF, WACC,
terminal value, and every ratio to be unit-tested against manually verified
expected outputs. That's only tractable if the math is isolated from the
database and the web framework — `tests/test_dcf.py` constructs a
`DCFAssumptions` with round numbers, computes the expected FCF/terminal
value/enterprise value/equity value/share price by hand in the docstring,
and asserts the engine matches to 6 decimal places. None of that requires
spinning up a database or an HTTP server.
