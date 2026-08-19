"""
Investment research report generator.

Builds the 14 sections from the spec. Every numeric section is generated
deterministically from the data the app already has (financials, ratios,
DCF, comps) — nothing here is fabricated or left to an LLM to "fill in."
An AI-generated narrative (Executive Summary, Key Catalysts, Key Risks
commentary) is optional and always labeled as AI-generated when included,
per the spec's requirement to separate facts, assumptions, and commentary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ReportInputs:
    company: dict
    financials_by_year: dict          # {fy: {income, balance, cash_flow}}
    ratios_by_year: dict              # {fy: {ratio: value}}
    dcf_result: dict | None = None
    dcf_assumptions: dict | None = None
    scenarios: dict | None = None     # {"bear": {...}, "base": {...}, "bull": {...}}
    comparables: dict | None = None
    data_mode: str = "demo"
    ai_narrative: dict | None = None  # optional: {"executive_summary": "...", "catalysts": [...], "risks": [...]}


def _fmt_money(v) -> str:
    if v is None:
        return "n/a"
    return f"${v:,.1f}M"


def _fmt_pct(v) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%"


def build_report(inputs: ReportInputs) -> dict:
    sections: dict[str, str] = {}
    demo_notice = (
        "⚠ DEMO MODE: figures in this report are illustrative synthetic data, not "
        "the company's actual reported financials.\n\n" if inputs.data_mode == "demo" else ""
    )

    years_sorted = sorted(inputs.financials_by_year.keys())
    latest_fy = years_sorted[-1]
    latest_fin = inputs.financials_by_year[latest_fy]
    latest_ratios = inputs.ratios_by_year.get(latest_fy, {})

    # 1. Executive Summary
    if inputs.ai_narrative and inputs.ai_narrative.get("executive_summary"):
        sections["executive_summary"] = (
            demo_notice + "[AI-GENERATED COMMENTARY]\n" + inputs.ai_narrative["executive_summary"]
        )
    else:
        rev = latest_fin["income"].get("revenue")
        margin = latest_ratios.get("net_margin")
        sections["executive_summary"] = (
            demo_notice
            + f"{inputs.company.get('name')} ({inputs.company.get('ticker')}) reported FY{latest_fy} "
              f"revenue of {_fmt_money(rev)} with a net margin of {_fmt_pct(margin)}. "
              "See the Valuation Summary section for DCF- and comparables-based implied value."
        )

    # 2. Company Overview
    sections["company_overview"] = demo_notice + "\n".join(
        f"{k}: {v}" for k, v in inputs.company.items()
    )

    # 3. Historical Financial Performance
    lines = [demo_notice.rstrip(), f"Fiscal years covered: {years_sorted[0]}–{years_sorted[-1]}\n"]
    for fy in years_sorted:
        inc = inputs.financials_by_year[fy]["income"]
        lines.append(
            f"FY{fy}: Revenue {_fmt_money(inc.get('revenue'))}, EBITDA {_fmt_money(inc.get('ebitda'))}, "
            f"Net Income {_fmt_money(inc.get('net_income'))}"
        )
    sections["historical_financial_performance"] = "\n".join(lines)

    # 4. Key Financial Ratios
    lines = [demo_notice.rstrip()]
    for fy in years_sorted:
        r = inputs.ratios_by_year.get(fy, {})
        lines.append(
            f"FY{fy}: Gross {_fmt_pct(r.get('gross_margin'))} | Op {_fmt_pct(r.get('operating_margin'))} | "
            f"Net {_fmt_pct(r.get('net_margin'))} | ROE {_fmt_pct(r.get('roe'))} | ROIC {_fmt_pct(r.get('roic'))} | "
            f"D/E {r.get('debt_to_equity')} | Current Ratio {r.get('current_ratio')}"
        )
    sections["key_financial_ratios"] = "\n".join(lines)

    # 5. Growth Analysis
    growth_lines = [demo_notice.rstrip()]
    for fy in years_sorted:
        r = inputs.ratios_by_year.get(fy, {})
        growth_lines.append(f"FY{fy}: Revenue growth {_fmt_pct(r.get('revenue_growth'))}, EPS growth {_fmt_pct(r.get('eps_growth'))}")
    sections["growth_analysis"] = "\n".join(growth_lines)

    # 6. Profitability Analysis
    sections["profitability_analysis"] = (
        demo_notice
        + f"FY{latest_fy} margins — Gross: {_fmt_pct(latest_ratios.get('gross_margin'))}, "
          f"Operating: {_fmt_pct(latest_ratios.get('operating_margin'))}, "
          f"EBITDA: {_fmt_pct(latest_ratios.get('ebitda_margin'))}, "
          f"Net: {_fmt_pct(latest_ratios.get('net_margin'))}, "
          f"FCF margin: {_fmt_pct(latest_ratios.get('fcf_margin'))}. "
          f"ROE: {_fmt_pct(latest_ratios.get('roe'))}, ROIC: {_fmt_pct(latest_ratios.get('roic'))}."
    )

    # 7. DCF Valuation
    if inputs.dcf_result:
        d = inputs.dcf_result
        sections["dcf_valuation"] = (
            demo_notice
            + f"Enterprise Value: {_fmt_money(d.get('enterprise_value'))}\n"
              f"Equity Value: {_fmt_money(d.get('equity_value'))}\n"
              f"Implied Share Price: ${d.get('implied_share_price'):.2f}\n"
              f"PV of forecast FCF: {_fmt_money(d.get('sum_pv_fcf'))}\n"
              f"PV of Terminal Value: {_fmt_money(d.get('pv_terminal_value'))}\n"
              "Methodology: FCF = EBIT x (1 - tax rate) + D&A - CapEx - Change in NWC, discounted "
              "at WACC; terminal value via Gordon Growth. See Methodology section."
        )
    else:
        sections["dcf_valuation"] = "No DCF has been run for this company yet."

    # 8. Comparable Company Valuation
    if inputs.comparables:
        c = inputs.comparables
        sections["comparable_company_valuation"] = (
            demo_notice
            + f"Median P/E: {c.get('median_pe')}, Median EV/EBITDA: {c.get('median_ev_ebitda')}, "
              f"Median EV/Revenue: {c.get('median_ev_revenue')}\n"
              f"Implied price (P/E): ${c.get('implied_price_from_pe')}\n"
              f"Implied price (EV/EBITDA): ${c.get('implied_price_from_ev_ebitda')}\n"
              f"Implied price (EV/Revenue): ${c.get('implied_price_from_ev_revenue')}\n"
              f"{c.get('methodology_note', '')}"
        )
    else:
        sections["comparable_company_valuation"] = "No comparable company analysis has been run yet."

    # 9. Bull/Base/Bear Scenarios
    if inputs.scenarios:
        lines = [demo_notice.rstrip()]
        for name in ("bear", "base", "bull"):
            s = inputs.scenarios.get(name)
            if s:
                lines.append(f"{name.title()}: implied price ${s.get('implied_share_price'):.2f}")
        sections["scenarios"] = "\n".join(lines)
    else:
        sections["scenarios"] = "No scenario analysis has been run yet."

    # 10. Key Catalysts
    if inputs.ai_narrative and inputs.ai_narrative.get("catalysts"):
        sections["key_catalysts"] = "[AI-GENERATED COMMENTARY]\n" + "\n".join(
            f"- {c}" for c in inputs.ai_narrative["catalysts"]
        )
    else:
        sections["key_catalysts"] = "Not generated. Enable the AI research assistant to draft catalyst commentary from the structured financial context."

    # 11. Key Risks
    if inputs.ai_narrative and inputs.ai_narrative.get("risks"):
        sections["key_risks"] = "[AI-GENERATED COMMENTARY]\n" + "\n".join(
            f"- {r}" for r in inputs.ai_narrative["risks"]
        )
    else:
        sections["key_risks"] = (
            "Quantitative risk flags: "
            + f"Net Debt/EBITDA {latest_ratios.get('net_debt_to_ebitda')}, "
            + f"Current Ratio {latest_ratios.get('current_ratio')}, "
            + f"Debt/Equity {latest_ratios.get('debt_to_equity')}."
        )

    # 12. Valuation Summary
    summary_prices = []
    if inputs.dcf_result:
        summary_prices.append(("DCF", inputs.dcf_result.get("implied_share_price")))
    if inputs.comparables:
        for label, key in [
            ("Comps (P/E)", "implied_price_from_pe"),
            ("Comps (EV/EBITDA)", "implied_price_from_ev_ebitda"),
            ("Comps (EV/Revenue)", "implied_price_from_ev_revenue"),
        ]:
            v = inputs.comparables.get(key)
            if v is not None:
                summary_prices.append((label, v))
    lines = [demo_notice.rstrip()] + [f"{label}: ${v:.2f}" for label, v in summary_prices if v is not None]
    sections["valuation_summary"] = "\n".join(lines) if len(lines) > 1 else demo_notice + "No valuations have been run yet."

    # 13. Methodology
    sections["methodology"] = (
        "DCF: FCF = EBIT x (1 - tax rate) + D&A - CapEx - Change in NWC, discounted at WACC. "
        "Terminal value via Gordon Growth: TV = FCF_(n+1) / (WACC - terminal growth). "
        "Comparables: median peer multiple x subject fundamental, EV multiples bridged to equity "
        "value via net debt. Ratios: standard formulas, see docs/FINANCIAL_MODEL.md for exact "
        "definitions of every line item used."
    )

    # 14. Data Sources
    sections["data_sources"] = (
        f"Data mode: {inputs.data_mode.upper()}. "
        + (
            "All financial statement and market data in this report are synthetic demo figures "
            "generated by MockProvider, not sourced from any real filing or market feed."
            if inputs.data_mode == "demo"
            else "Financial statement and market data sourced from the configured live financial data provider."
        )
    )

    return {
        "title": f"{inputs.company.get('name')} ({inputs.company.get('ticker')}) — Investment Research Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": inputs.data_mode,
        "sections": sections,
    }
