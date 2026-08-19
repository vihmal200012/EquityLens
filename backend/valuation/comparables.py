"""
Comparable company ("comps") analysis.

For each peer we compute standard trading multiples, then apply the
median (and mean, for reference) multiple to the subject company's own
fundamentals to back into an implied valuation. Median is used as the
primary estimate because it's less distorted by an outlier peer than the
mean — this is stated explicitly in the result so the report can explain
its own methodology.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class PeerFinancials:
    ticker: str
    price: float
    shares_outstanding: float
    net_income: float
    ebitda: float
    revenue: float
    total_debt: float
    cash: float
    free_cash_flow: float
    revenue_prior_year: float | None = None

    @property
    def market_cap(self) -> float:
        return self.price * self.shares_outstanding

    @property
    def enterprise_value(self) -> float:
        return self.market_cap + self.total_debt - self.cash


@dataclass
class PeerMultiples:
    ticker: str
    pe: float | None
    ev_ebitda: float | None
    ev_revenue: float | None
    price_sales: float | None
    fcf_yield: float | None
    revenue_growth: float | None
    ebitda_margin: float | None


def _safe_div(n, d):
    if n is None or d is None or d == 0:
        return None
    return n / d


def compute_peer_multiples(peer: PeerFinancials) -> PeerMultiples:
    revenue_growth = None
    if peer.revenue_prior_year:
        revenue_growth = _safe_div(peer.revenue - peer.revenue_prior_year, peer.revenue_prior_year)

    return PeerMultiples(
        ticker=peer.ticker,
        pe=_safe_div(peer.market_cap, peer.net_income),
        ev_ebitda=_safe_div(peer.enterprise_value, peer.ebitda),
        ev_revenue=_safe_div(peer.enterprise_value, peer.revenue),
        price_sales=_safe_div(peer.market_cap, peer.revenue),
        fcf_yield=_safe_div(peer.free_cash_flow, peer.market_cap),
        revenue_growth=revenue_growth,
        ebitda_margin=_safe_div(peer.ebitda, peer.revenue),
    )


@dataclass
class ComparableValuationResult:
    peer_multiples: list[PeerMultiples]
    median_pe: float | None
    mean_pe: float | None
    median_ev_ebitda: float | None
    mean_ev_ebitda: float | None
    median_ev_revenue: float | None
    mean_ev_revenue: float | None
    implied_price_from_pe: float | None
    implied_price_from_ev_ebitda: float | None
    implied_price_from_ev_revenue: float | None
    methodology_note: str


def _median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def _mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.mean(clean) if clean else None


def run_comparable_valuation(
    peers: list[PeerFinancials],
    subject_net_income: float,
    subject_ebitda: float,
    subject_revenue: float,
    subject_net_debt: float,
    subject_shares_outstanding: float,
) -> ComparableValuationResult:
    if not peers:
        raise ValueError("At least one comparable company is required.")

    multiples = [compute_peer_multiples(p) for p in peers]

    median_pe = _median([m.pe for m in multiples])
    mean_pe = _mean([m.pe for m in multiples])
    median_ev_ebitda = _median([m.ev_ebitda for m in multiples])
    mean_ev_ebitda = _mean([m.ev_ebitda for m in multiples])
    median_ev_revenue = _median([m.ev_revenue for m in multiples])
    mean_ev_revenue = _mean([m.ev_revenue for m in multiples])

    implied_price_pe = None
    if median_pe is not None:
        implied_equity_value = median_pe * subject_net_income
        implied_price_pe = implied_equity_value / subject_shares_outstanding

    implied_price_ev_ebitda = None
    if median_ev_ebitda is not None:
        implied_ev = median_ev_ebitda * subject_ebitda
        implied_equity_value = implied_ev - subject_net_debt
        implied_price_ev_ebitda = implied_equity_value / subject_shares_outstanding

    implied_price_ev_revenue = None
    if median_ev_revenue is not None:
        implied_ev = median_ev_revenue * subject_revenue
        implied_equity_value = implied_ev - subject_net_debt
        implied_price_ev_revenue = implied_equity_value / subject_shares_outstanding

    note = (
        "Implied share price = median peer multiple x subject company's own metric "
        "(net income for P/E; EBITDA or revenue for EV multiples, then bridged to equity "
        "value by subtracting net debt). Median is used as the primary estimate because it "
        "is less sensitive to a single outlier peer than the mean; the mean is shown for "
        "reference alongside it."
    )

    return ComparableValuationResult(
        peer_multiples=multiples,
        median_pe=median_pe,
        mean_pe=mean_pe,
        median_ev_ebitda=median_ev_ebitda,
        mean_ev_ebitda=mean_ev_ebitda,
        median_ev_revenue=median_ev_revenue,
        mean_ev_revenue=mean_ev_revenue,
        implied_price_from_pe=implied_price_pe,
        implied_price_from_ev_ebitda=implied_price_ev_ebitda,
        implied_price_from_ev_revenue=implied_price_ev_revenue,
        methodology_note=note,
    )
