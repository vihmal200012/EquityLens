from backend.reports.generator import ReportInputs, build_report

EXPECTED_SECTIONS = {
    "executive_summary",
    "company_overview",
    "historical_financial_performance",
    "key_financial_ratios",
    "growth_analysis",
    "profitability_analysis",
    "dcf_valuation",
    "comparable_company_valuation",
    "scenarios",
    "key_catalysts",
    "key_risks",
    "valuation_summary",
    "methodology",
    "data_sources",
}


def make_inputs(**overrides):
    defaults = dict(
        company={"ticker": "DEMO", "name": "Demo Co (demo data)", "sector": "Technology"},
        financials_by_year={
            2023: {"income": {"revenue": 900.0, "ebitda": 200.0, "net_income": 100.0}, "balance": {}, "cash_flow": {}},
            2024: {"income": {"revenue": 1000.0, "ebitda": 250.0, "net_income": 144.0}, "balance": {}, "cash_flow": {}},
        },
        ratios_by_year={
            2023: {"gross_margin": 0.38, "revenue_growth": None},
            2024: {"gross_margin": 0.40, "revenue_growth": 0.111, "net_margin": 0.144, "roe": 0.24, "roic": 0.20},
        },
        data_mode="demo",
    )
    defaults.update(overrides)
    return ReportInputs(**defaults)


def test_all_14_sections_present():
    report = build_report(make_inputs())
    assert set(report["sections"].keys()) == EXPECTED_SECTIONS


def test_demo_notice_appears_when_data_mode_is_demo():
    report = build_report(make_inputs())
    assert "DEMO MODE" in report["sections"]["company_overview"]


def test_no_demo_notice_when_live():
    report = build_report(make_inputs(data_mode="live_api"))
    assert "DEMO MODE" not in report["sections"]["company_overview"]
    assert "live" in report["sections"]["data_sources"].lower()


def test_ai_narrative_labeled_when_present():
    report = build_report(
        make_inputs(
            ai_narrative={
                "executive_summary": "Demo Co shows steady margin expansion.",
                "risks": ["Customer concentration risk"],
                "catalysts": ["New product cycle"],
            }
        )
    )
    assert "[AI-GENERATED COMMENTARY]" in report["sections"]["executive_summary"]
    assert "[AI-GENERATED COMMENTARY]" in report["sections"]["key_risks"]
    assert "[AI-GENERATED COMMENTARY]" in report["sections"]["key_catalysts"]


def test_scenarios_section_renders_bear_base_bull_prices():
    """The scenarios section expects the flat {"bear": {...}, "base": {...},
    "bull": {...}} shape documented on ReportInputs.scenarios — NOT the full
    /dcf/scenarios response envelope ({ticker, data_mode, scenarios: {...}})."""
    report = build_report(
        make_inputs(
            scenarios={
                "bear": {"implied_share_price": 65.90},
                "base": {"implied_share_price": 97.63},
                "bull": {"implied_share_price": 150.82},
            }
        )
    )
    section = report["sections"]["scenarios"]
    assert "Bear: implied price $65.90" in section
    assert "Base: implied price $97.63" in section
    assert "Bull: implied price $150.82" in section


def test_ratios_and_comparables_are_rounded_for_presentation():
    """Regression test: debt_to_equity/current_ratio/net_debt_to_ebitda and
    comparables multiples/implied prices used to be interpolated as raw
    floats (e.g. "0.24692826264011886"), not the underlying calculation.
    Presentation should round to 2dp without changing the computed value."""
    report = build_report(
        make_inputs(
            ratios_by_year={
                2023: {"gross_margin": 0.38, "revenue_growth": None},
                2024: {
                    "gross_margin": 0.40,
                    "revenue_growth": 0.111,
                    "net_margin": 0.144,
                    "roe": 0.24,
                    "roic": 0.20,
                    "debt_to_equity": 0.24692826264011886,
                    "current_ratio": 2.3356293348425603,
                    "net_debt_to_ebitda": 0.3556658395368073,
                },
            },
            comparables={
                "median_pe": 7.284090909090909,
                "median_ev_ebitda": 7.284090909090909,
                "median_ev_revenue": 1.6111111111111112,
                "implied_price_from_pe": 71.41291612903225,
                "implied_price_from_ev_ebitda": None,
            },
        )
    )
    ratios_section = report["sections"]["key_financial_ratios"]
    risks_section = report["sections"]["key_risks"]
    comps_section = report["sections"]["comparable_company_valuation"]

    assert "D/E 0.25" in ratios_section
    assert "Current Ratio 2.34" in ratios_section
    assert "Debt/Equity 0.25" in risks_section
    assert "Net Debt/EBITDA 0.36" in risks_section
    assert "Median P/E: 7.28" in comps_section
    assert "Implied price (P/E): $71.41" in comps_section
    assert "Implied price (EV/EBITDA): n/a" in comps_section

    for section in (ratios_section, risks_section, comps_section):
        assert "26264011886" not in section
        assert "090909090909" not in section


def test_valuation_summary_reflects_dcf_and_comps():
    report = build_report(
        make_inputs(
            dcf_result={"implied_share_price": 16.0, "enterprise_value": 1800.0, "equity_value": 1600.0, "sum_pv_fcf": 130.9, "pv_terminal_value": 1669.1},
            comparables={"implied_price_from_pe": 18.5, "median_pe": 15.0},
        )
    )
    assert "DCF: $16.00" in report["sections"]["valuation_summary"]
    assert "Comps (P/E): $18.50" in report["sections"]["valuation_summary"]
