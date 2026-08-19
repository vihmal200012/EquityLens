# EquityLens

**AI-Powered Equity Research & Valuation Terminal** — a backend engine and
API for real equity research: financial statement analysis, a genuine DCF
model, comparable-company analysis, portfolio analytics, an AI research
assistant grounded in structured financial data, and investment research
report generation.

> **Status: Phase 1 of the frontend is not built yet.** This is the
> foundation layer — database, provider abstraction, financial engine,
> valuation engine, portfolio analytics, AI layer, report generator, and a
> full FastAPI backend, all with unit + API tests. It's usable today via
> the API (or `curl`/Postman/the interactive `/docs` page); a web frontend
> is the natural next phase. See **Limitations** below.

## Why this exists

This is a portfolio project meant to demonstrate real financial modeling,
not a toy stock dashboard. Every valuation number is either:
- **Historical fact** (from a `FinancialDataProvider`),
- **A stated assumption** (revenue growth, margins, WACC, terminal growth — all
  explicit inputs, never hidden defaults), or
- **A calculation** derived from the two above, using textbook formulas.

Nothing is fabricated. In DEMO MODE (no API key configured), every record
is tagged `source: "demo"` end-to-end — in the database, the API responses,
and the AI assistant's context — and the AI is instructed to say so before
answering any quantitative question.

## Architecture

```
backend/
  database/       SQLAlchemy models + session + seed script (9 tables)
  providers/       FinancialDataProvider interface + MockProvider (demo) + LiveProvider (real API)
  financial_engine/  Ratio calculations (pure functions, no I/O)
  valuation/       DCF engine + comparable company analysis (pure functions)
  portfolio/       Return/vol/Sharpe/drawdown/beta/correlation (pure functions)
  ai/              Structured context builder + Anthropic API client
  reports/         Deterministic 14-section report generator
  api/             FastAPI app wiring it all into REST endpoints
tests/             57 unit tests + 18 API tests (75 total), all passing
docs/              Architecture, financial model, data sources, AI design
```

The financial engine, valuation engine, and portfolio engine are all pure
functions with no database or network dependency — that's what makes them
independently unit-testable against hand-computed expected values (see
`tests/test_dcf.py` for a fully worked example).

## Features implemented

- **Company profile & market data** via provider abstraction (demo or live)
- **5-year financial statements**: income statement, balance sheet, cash flow
- **Ratio engine**: revenue growth, gross/operating/net/EBITDA margin, EPS
  growth, FCF & FCF margin, ROE, ROIC, debt/equity, net debt/EBITDA, current ratio
- **DCF valuation engine**: FCF build-up, Gordon Growth terminal value,
  enterprise → equity value → implied share price, with input validation
  (e.g. rejects WACC ≤ terminal growth)
- **Bear/base/bull scenario analysis**
- **Two-variable WACC × terminal-growth sensitivity table**
- **Comparable company analysis**: P/E, EV/EBITDA, EV/Revenue, Price/Sales,
  FCF yield; median/mean multiples; implied valuation bridged through net debt
- **Portfolio analytics**: total/annualized return, volatility, Sharpe ratio,
  max drawdown, beta, correlation matrix, position weights
- **AI research assistant**: answers questions using a structured context
  object built from the same data as everything else — never free web search,
  never invented numbers (see `docs/AI_DESIGN.md`)
- **Investment research report generator**: all 14 sections from the spec,
  deterministic where possible, clearly labeled `[AI-GENERATED COMMENTARY]`
  where an LLM narrative is included

## Financial methodology (summary — see `docs/FINANCIAL_MODEL.md`)

```
FCF_t = EBIT_t x (1 - tax rate) + D&A_t - CapEx_t - Change in NWC_t
PV of FCF_t = FCF_t / (1 + WACC)^t
Terminal Value = FCF_(n+1) / (WACC - terminal growth)
Enterprise Value = sum(PV of FCF_1..n) + PV(Terminal Value)
Equity Value = Enterprise Value - Net Debt
Implied Share Price = Equity Value / Diluted Shares Outstanding
```

## Data sources

By default the app runs in **DEMO MODE**: `MockProvider` generates
internally-consistent synthetic 5-year financials for AAPL, MSFT, and NVDA
(balance sheets balance, cash flow ties to net income, etc.), loosely scaled
to real company size for realism — but these are **not** the companies'
actual reported financials, and every response says so explicitly.

Set `FINANCIAL_API_KEY` to switch to `LiveProvider`, a working adapter
skeleton for a Financial-Modeling-Prep-style REST API (see
`backend/providers/live_provider.py`). Swap in whatever real provider you
have a key for by implementing the same `FinancialDataProvider` interface —
nothing else in the app needs to change.

## AI architecture (summary — see `docs/AI_DESIGN.md`)

The AI never free-searches or answers from parametric memory about the
company. Every request builds an explicit `AIContext` (company profile,
financial statements, ratios, valuation, assumptions, comparables) and
renders it as a text block prepended to the question. The system prompt
requires the model to separate fact from interpretation, cite the provided
numbers, name assumptions, and state uncertainty — see
`backend/ai/context.py` for the exact prompt.

## Installation

```bash
git clone <this repo>
cd equitylens
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys if you have them; demo mode works with none
python -m backend.database.seed   # optional: pre-populate the DB with demo companies
uvicorn backend.api.main:app --reload
```

Then open `http://localhost:8000/docs` for the interactive API explorer, or:

```bash
curl http://localhost:8000/api/companies/AAPL
curl http://localhost:8000/api/companies/AAPL/ratios
curl -X POST http://localhost:8000/api/companies/AAPL/dcf -H "Content-Type: application/json" -d '{
  "revenue_growth_rates": [0.08, 0.07, 0.06, 0.05, 0.04],
  "ebit_margin": 0.28, "tax_rate": 0.15, "da_pct_revenue": 0.03,
  "capex_pct_revenue": 0.03, "nwc_pct_revenue_change": 0.10,
  "wacc": 0.09, "terminal_growth": 0.025
}'
```

## Environment variables

| Variable | Required? | Effect if unset |
|---|---|---|
| `FINANCIAL_API_KEY` | No | Falls back to DEMO MODE (`MockProvider`) |
| `AI_API_KEY` | No | AI assistant endpoint returns `503` with a clear message |
| `DATABASE_URL` | No | Defaults to local SQLite (`./equitylens.db`) |

Never hardcode keys anywhere in the codebase — everything reads from these
environment variables via `os.environ`.

## Testing

```bash
pytest tests/ -v
```

75 tests, all passing: 57 unit tests (ratios, DCF, comparables, portfolio,
reports, database models) plus 18 API tests, including an end-to-end test
that mirrors the spec's required flow: search AAPL → load financials →
compute ratios → run DCF → generate report.

Every DCF test is checked against a fully hand-computed example (see the
docstring in `tests/test_dcf.py`) — not just "does it run," but "does it
produce the mathematically correct number."

## Example screenshots

No frontend exists yet (see Limitations), so there's nothing to screenshot.
The interactive API docs at `/docs` (FastAPI's auto-generated Swagger UI)
are the closest thing to a UI right now.

## Limitations

- **No frontend yet.** This phase is the data/engine/API layer. The pages
  described in the original spec (`/dashboard`, `/company/[ticker]`, etc.)
  haven't been built.
- **DEMO MODE data is synthetic**, not real filings — clearly labeled, but
  worth repeating: don't use these numbers for actual investment decisions.
- **`LiveProvider` is a working skeleton**, not validated against a live
  key/response in this environment — the request/response shape matches a
  Financial-Modeling-Prep-style API but hasn't been tested against a real key.
- **No auth/user accounts** — the API is currently open; add an auth layer
  before deploying anywhere multi-user.
- **Rate limiting is in-memory** (per-process), fine for a single instance,
  not for a horizontally-scaled deployment — swap for Redis-backed limiting
  if you scale out.
- **Portfolio annualization assumes daily prices** (252 periods/year) — feed
  it daily closes, not monthly or weekly, or override `periods_per_year`.
- **PDF export for reports isn't implemented** — `generate_report` returns
  structured JSON; wiring that into a PDF is a frontend/reporting task.

## Suggested next improvements

1. Build the frontend (Next.js/React, per the original architecture) against
   this API — dashboard, company page with tabs, sensitivity heatmap, etc.
2. Wire `LiveProvider` up to a real key and validate against actual API responses.
3. Add PDF export of the research report (e.g. via WeasyPrint or a headless
   browser rendering a report template).
4. Add auth (API keys or JWT) before any multi-user deployment.
5. Backtesting framework: replay historical DCF assumptions against
   subsequent actual price performance.
6. Persist AI Q&A and generated reports to the `research_reports` table
   (the schema supports it; the API doesn't write to it yet).
7. WACC auto-calculation endpoint using live beta/risk-free-rate data,
   rather than requiring the caller to compute WACC before calling `/dcf`.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/FINANCIAL_MODEL.md`](docs/FINANCIAL_MODEL.md)
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)
- [`docs/AI_DESIGN.md`](docs/AI_DESIGN.md)
