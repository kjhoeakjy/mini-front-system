import math
from datetime import date

import pytest

from app.quant.black_scholes import bsm, position_greeks, year_fraction

BASE = dict(S=100.0, K=100.0, T=1.0, r=0.05, q=0.0, sigma=0.20)


def test_known_values():
    assert bsm("CALL", **BASE).price == pytest.approx(10.450583572185565, abs=1e-10)
    assert bsm("PUT", **BASE).price == pytest.approx(5.573526022256971, abs=1e-10)


def test_bounds_and_signs():
    for S in (60, 100, 140):
        for q in (0.0, 0.03):
            kw = dict(BASE, S=S, q=q)
            c, p = bsm("CALL", **kw), bsm("PUT", **kw)
            assert 0 <= c.price <= S * math.exp(-q * kw["T"])
            assert 0 <= p.price <= kw["K"] * math.exp(-kw["r"] * kw["T"])
            assert c.delta >= 0 and p.delta <= 0 and c.gamma >= 0 and c.vega_raw >= 0
            assert c.gamma == pytest.approx(p.gamma) and c.vega_raw == pytest.approx(p.vega_raw)


@pytest.mark.parametrize("ot", ["CALL", "PUT"])
@pytest.mark.parametrize("q,r", [(0.0, 0.05), (0.02, 0.03), (0.01, -0.01)])
def test_analytic_vs_central_difference(ot, q, r):
    kw = dict(S=105.0, K=100.0, T=0.75, r=r, q=q, sigma=0.25)
    g = bsm(ot, **kw)
    f = lambda **o: bsm(ot, **{**kw, **o}).price
    hS, hv, hr, ht = 1e-3, 1e-5, 1e-5, 1e-5   # 유한차분 간격
    assert g.delta == pytest.approx((f(S=kw["S"] + hS) - f(S=kw["S"] - hS)) / (2 * hS), abs=1e-6)
    assert g.gamma == pytest.approx((f(S=kw["S"] + hS) - 2 * f() + f(S=kw["S"] - hS)) / hS ** 2, abs=1e-4)
    assert g.vega_raw == pytest.approx((f(sigma=kw["sigma"] + hv) - f(sigma=kw["sigma"] - hv)) / (2 * hv), abs=1e-5)
    assert g.rho_raw == pytest.approx((f(r=r + hr) - f(r=r - hr)) / (2 * hr), abs=1e-5)
    assert g.theta_annual == pytest.approx(-(f(T=kw["T"] + ht) - f(T=kw["T"] - ht)) / (2 * ht), abs=1e-5)


def test_long_short_sign_and_multiplier():
    res = bsm("CALL", **BASE)
    long_, short = position_greeks(res, 100, 1), position_greeks(res, 100, -1)
    for k in long_:
        assert long_[k] == pytest.approx(-short[k])
    assert long_["delta_shares"] == pytest.approx(res.delta * 100)
    assert long_["vega_per_1volpt_usd"] == pytest.approx(res.vega_raw * 0.01 * 100)
    assert long_["rho_per_100bp_usd"] == pytest.approx(res.rho_raw * 0.01 * 100)
    assert long_["theta_per_calendar_day_usd"] == pytest.approx(res.theta_annual / 365 * 100)


def test_unit_definitions_match_repricing():
    res = bsm("CALL", **BASE)
    g = position_greeks(res, 100, 1)
    up_vol = (bsm("CALL", **dict(BASE, sigma=0.21)).price - res.price) * 100
    up_rate = (bsm("CALL", **dict(BASE, r=0.06)).price - res.price) * 100
    assert g["vega_per_1volpt_usd"] == pytest.approx(up_vol, rel=0.01)
    assert g["rho_per_100bp_usd"] == pytest.approx(up_rate, rel=0.02)


def test_edge_cases():
    assert bsm("CALL", 110, 100, 0, 0.05, 0, 0.2).price == 10 and bsm("CALL", 110, 100, 0, 0.05, 0, 0.2).delta is None
    assert bsm("PUT", 90, 100, -0.1, 0.05, 0, 0.2).price == 10
    z = bsm("CALL", 100, 90, 1, 0.05, 0.0, 0.0)
    assert z.price == pytest.approx(100 - 90 * math.exp(-0.05)) and z.gamma == 0
    assert bsm("PUT", 100, 90, 1, 0.05, 0.0, 0.0).price == 0
    assert bsm("CALL", 100, 100, 1, -0.01, 0.0, 0.2).price > 0
    assert bsm("CALL", 100, 1e6, 1, 0.05, 0, 0.2).price == pytest.approx(0, abs=1e-12)
    for bad in (dict(S=-1), dict(K=0), dict(sigma=-0.1)):
        with pytest.raises(ValueError):
            bsm("CALL", **{**BASE, **bad})
    with pytest.raises(ValueError):
        bsm("STRADDLE", **BASE)


def test_year_fraction_uses_actual_days():
    assert year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(1.0)
