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


def test_valuation_summary_reflects_dcf_and_comps():
    report = build_report(
        make_inputs(
            dcf_result={"implied_share_price": 16.0, "enterprise_value": 1800.0, "equity_value": 1600.0, "sum_pv_fcf": 130.9, "pv_terminal_value": 1669.1},
            comparables={"implied_price_from_pe": 18.5, "median_pe": 15.0},
        )
    )
    assert "DCF: $16.00" in report["sections"]["valuation_summary"]
    assert "Comps (P/E): $18.50" in report["sections"]["valuation_summary"]
