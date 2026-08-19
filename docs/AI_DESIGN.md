# AI Assistant Design

## Principle

The AI research assistant answers questions **only** from a structured
context object built by EquityLens itself — it never free-searches the web
and is never asked to recall a company's financials from its own training
data. If a number isn't in the context, the system prompt instructs it to
say so rather than fill the gap from memory.

## The context object

`backend/ai/context.py` defines `AIContext`:

```python
AIContext(
    company={...},        # ticker, name, sector, industry
    financials={...},     # {fiscal_year: {income_statement, balance_sheet, cash_flow}}
    ratios={...},         # {fiscal_year: {ratio_name: value_or_None}}
    valuation={...},      # latest DCF result, if one has been run
    assumptions={...},    # the exact assumptions behind that DCF
    comparables={...},    # comps result, if run
    risks=[...],          # any flagged risk strings
    data_mode="demo",     # surfaced to the model explicitly
)
```

This mirrors the spec's example structure exactly
(`{company, financials, ratios, valuation, assumptions, comparables, risks}`).
`render_context_block()` turns it into a deterministic, fully-enumerated
text block — every fiscal year, every ratio, every line item, nothing
summarized or dropped before the model sees it.

## System prompt

The system prompt (`SYSTEM_PROMPT` in `context.py`) requires the model to:

1. Use only the provided context — never invent, estimate, or recall
   figures from general knowledge.
2. Disclose DEMO MODE explicitly before answering quantitative questions,
   when `data_mode == "demo"`.
3. Separate **facts** (numbers straight from context) from
   **interpretation** (the model's analysis), and label which is which.
4. Show the actual calculation path (using real numbers from `valuation`/
   `assumptions`) rather than describing the DCF abstractly.
5. Name the assumptions behind any valuation figure it cites.
6. State uncertainty explicitly — a DCF is a model of assumptions, not a
   guaranteed price target, and the assistant is instructed never to imply
   otherwise.
7. Say plainly when a question is out of scope (news, management changes,
   macro events) rather than guessing.

## Request flow

`POST /api/companies/{ticker}/ai/ask`:

1. Rate-limited (`_check_rate_limit`, 10 requests / 60s per client IP) since
   this is the most expensive endpoint in the app.
2. Loads 5 years of financials + computed ratios via the same
   `_load_years()` / `compute_ratio_series()` path every other endpoint uses
   — the AI sees exactly the same numbers a human would see in the UI, not
   a separately-fetched or separately-computed version.
3. Builds an `AIContext`, instantiates `ResearchAssistant`, calls `.ask()`.
4. `ResearchAssistant.ask()` reads `AI_API_KEY` from the environment; if
   unset, raises `AIUnavailableError` and the endpoint returns `503` with a
   clear message — no silent fallback to a canned or fabricated answer.
5. The question string is minimally sanitized (strips null bytes) before
   being sent — see Security notes below.

## Security notes

- `AI_API_KEY` is never exposed to any frontend; it's read server-side only.
- User questions are inserted into the prompt as the `QUESTION:` section
  after a fixed `CONTEXT:` section — the system prompt's instructions
  (use only provided context, don't invent numbers) are the primary defense
  against a user trying to get the model to fabricate figures or ignore
  its constraints via prompt injection in the question text.
- The AI endpoint is rate-limited separately from the rest of the API since
  it's the only one that costs money per call.

## What isn't built yet

- Conversation history / multi-turn chat (each `/ai/ask` call is stateless).
- Persisting AI answers to the `research_reports` table (schema supports an
  `ai_assisted` flag; the endpoint doesn't write to the DB yet).
- Streaming responses.
