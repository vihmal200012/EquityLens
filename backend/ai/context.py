"""
Builds the structured context object the AI research assistant is given.
The AI never free-searches the internet or invents figures — it only sees
what's assembled here, straight from the DB/valuation engine. This module
also renders that context into the prompt text sent to the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIContext:
    company: dict
    financials: dict            # {fiscal_year: {income, balance, cash_flow}}
    ratios: dict                # {fiscal_year: {ratio_name: value}}
    valuation: dict | None = None       # latest DCF result, if one has been run
    assumptions: dict | None = None     # the assumptions behind that DCF
    comparables: dict | None = None     # comps result, if run
    risks: list[str] = field(default_factory=list)
    data_mode: str = "demo"     # "demo" | "live_api" — surfaced to the model explicitly


SYSTEM_PROMPT = """You are EquityLens's equity research assistant.

Rules you must follow on every answer:
1. Use ONLY the structured financial data provided in the context block below.
   Never invent, estimate, or recall figures from general knowledge — if a
   number isn't in the context, say it isn't available rather than guessing.
2. When the data_mode field is "demo", state plainly that the underlying
   figures are illustrative demo data, not the company's real reported
   financials, before answering any quantitative question about them.
3. Separate FACTS (numbers straight from the context) from INTERPRETATION
   (your analysis of what they mean). Label which is which.
4. When asked about the DCF or valuation, show the calculation path using
   the actual numbers in `valuation`/`assumptions` rather than describing it
   abstractly.
5. Always name the assumptions behind any valuation figure you cite (growth
   rate, margin, WACC, terminal growth) so the reader can judge sensitivity.
6. State uncertainty and limitations explicitly — a DCF is a model of
   assumptions, not a guaranteed price target. Never claim a valuation
   output is a prediction or guarantee of future price.
7. If asked something the context doesn't cover (e.g. news, management
   changes, macro events), say this assistant only has the structured
   financial context, not live news or qualitative reporting.
"""


def render_context_block(ctx: AIContext) -> str:
    """Turn the structured context into the text block appended to the
    system/user prompt. Kept deterministic and explicit (no summarizing)
    so nothing is lost or distorted before the model sees it."""
    lines = [f"DATA MODE: {ctx.data_mode.upper()}"]
    if ctx.data_mode == "demo":
        lines.append(
            "NOTE: All figures below are illustrative synthetic demo data, "
            "not the company's actual reported financials."
        )

    lines.append("\n## Company")
    for k, v in ctx.company.items():
        lines.append(f"- {k}: {v}")

    lines.append("\n## Financials by fiscal year")
    for fy, statements in sorted(ctx.financials.items()):
        lines.append(f"\n### FY{fy}")
        for stmt_name, stmt_data in statements.items():
            lines.append(f"  {stmt_name}:")
            for k, v in stmt_data.items():
                lines.append(f"    - {k}: {v}")

    lines.append("\n## Ratios by fiscal year")
    for fy, ratio_set in sorted(ctx.ratios.items()):
        lines.append(f"\n### FY{fy}")
        for k, v in ratio_set.items():
            lines.append(f"  - {k}: {v if v is not None else 'n/a'}")

    if ctx.valuation:
        lines.append("\n## Latest DCF valuation")
        for k, v in ctx.valuation.items():
            lines.append(f"- {k}: {v}")

    if ctx.assumptions:
        lines.append("\n## DCF assumptions behind that valuation")
        for k, v in ctx.assumptions.items():
            lines.append(f"- {k}: {v}")

    if ctx.comparables:
        lines.append("\n## Comparable company analysis")
        for k, v in ctx.comparables.items():
            lines.append(f"- {k}: {v}")

    if ctx.risks:
        lines.append("\n## Flagged risks")
        for r in ctx.risks:
            lines.append(f"- {r}")

    return "\n".join(lines)
