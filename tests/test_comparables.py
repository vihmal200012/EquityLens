import pytest

from backend.valuation.comparables import (
    PeerFinancials,
    compute_peer_multiples,
    run_comparable_valuation,
)


def make_peer(ticker, price, shares, net_income, ebitda, revenue, debt, cash, fcf, rev_prior=None):
    return PeerFinancials(
        ticker=ticker,
        price=price,
        shares_outstanding=shares,
        net_income=net_income,
        ebitda=ebitda,
        revenue=revenue,
        total_debt=debt,
        cash=cash,
        free_cash_flow=fcf,
        revenue_prior_year=rev_prior,
    )


def test_peer_multiples_hand_calculation():
    # market cap = 50 * 20 = 1000; EV = 1000 + 100 - 50 = 1050
    peer = make_peer("PEERA", price=50, shares=20, net_income=100, ebitda=150, revenue=500, debt=100, cash=50, fcf=90, rev_prior=400)
    m = compute_peer_multiples(peer)
    assert m.pe == pytest.approx(10.0)          # 1000/100
    assert m.ev_ebitda == pytest.approx(7.0)     # 1050/150
    assert m.ev_revenue == pytest.approx(2.1)    # 1050/500
    assert m.price_sales == pytest.approx(2.0)   # 1000/500
    assert m.fcf_yield == pytest.approx(0.09)    # 90/1000
    assert m.revenue_growth == pytest.approx(0.25)  # (500-400)/400
    assert m.ebitda_margin == pytest.approx(0.30)   # 150/500


def test_median_multiple_used_for_implied_valuation():
    peers = [
        make_peer("A", price=100, shares=10, net_income=100, ebitda=150, revenue=500, debt=50, cash=20, fcf=80),  # PE=10
        make_peer("B", price=150, shares=10, net_income=100, ebitda=150, revenue=500, debt=50, cash=20, fcf=80),  # PE=15
        make_peer("C", price=200, shares=10, net_income=100, ebitda=150, revenue=500, debt=50, cash=20, fcf=80),  # PE=20
    ]
    result = run_comparable_valuation(
        peers,
        subject_net_income=200,
        subject_ebitda=300,
        subject_revenue=1000,
        subject_net_debt=100,
        subject_shares_outstanding=50,
    )
    assert result.median_pe == pytest.approx(15.0)
    # implied equity value = 15 * 200 = 3000; price = 3000/50 = 60
    assert result.implied_price_from_pe == pytest.approx(60.0)


def test_ev_ebitda_bridges_through_net_debt():
    peers = [make_peer("A", price=100, shares=10, net_income=80, ebitda=100, revenue=400, debt=0, cash=0, fcf=70)]
    # EV = 1000, EV/EBITDA = 10
    result = run_comparable_valuation(
        peers,
        subject_net_income=150,
        subject_ebitda=200,
        subject_revenue=900,
        subject_net_debt=300,
        subject_shares_outstanding=100,
    )
    # implied EV = 10 * 200 = 2000; equity value = 2000 - 300 = 1700; price = 17.0
    assert result.implied_price_from_ev_ebitda == pytest.approx(17.0)


def test_empty_peer_list_raises():
    with pytest.raises(ValueError):
        run_comparable_valuation([], 100, 100, 100, 0, 10)
