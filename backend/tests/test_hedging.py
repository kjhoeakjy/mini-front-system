from datetime import date, timedelta

import pytest

from app.quant.black_scholes import BsmResult, position_greeks
from app.quant.hedging import delta_hedge, hedge_backtest


def test_short_call_delta_060_needs_plus_60_shares():
    res = BsmResult(price=5.0, delta=0.60, gamma=0.02, vega_raw=10.0, theta_annual=-3.0, rho_raw=8.0, d1=0.25, d2=0.1)
    g = position_greeks(res, 100, -1)
    assert g["delta_shares"] == pytest.approx(-60.0)
    plan = delta_hedge({"SPY": g["delta_shares"], "QQQ": 0.0}, {"SPY": 500.0, "QQQ": 400.0}, {"SPY": 0.0, "QQQ": 0.0})
    assert plan["SPY"]["trade_shares"] == 60 and plan["SPY"]["side"] == "매수" and plan["SPY"]["net_delta_after"] == pytest.approx(0)
    assert plan["QQQ"]["trade_shares"] == 0 and plan["QQQ"]["estimated_cost"] == 0


def test_rounding_leaves_residual_and_cost():
    plan = delta_hedge({"SPY": -54.6, "QQQ": 12.3}, {"SPY": 500.0, "QQQ": 400.0}, {"SPY": 10.0, "QQQ": 0.0}, cost_bps=2.0, fixed_fee=1.0)
    assert plan["SPY"]["trade_shares"] == 55 and plan["SPY"]["net_delta_after"] == pytest.approx(0.4)
    assert plan["SPY"]["shares_after"] == 65 and plan["QQQ"]["side"] == "매도"
    assert plan["SPY"]["estimated_cost"] == pytest.approx(55 * 500 * 0.0002 + 1.0)
    exact = delta_hedge({"SPY": -54.6, "QQQ": 12.3}, {"SPY": 500.0, "QQQ": 400.0}, {"SPY": 0.0, "QQQ": 0.0}, integer_shares=False)
    assert exact["SPY"]["net_delta_after"] == pytest.approx(0)


def _dates(n):
    out, d = [], date(2025, 1, 1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_backtest_cash_account_no_hedge():
    ds = _dates(60)
    px = [100 + 0.5 * i for i in range(60)]
    r = hedge_backtest(ds, px, sigma=0.2, r=0.0, rebalance_every=0, cost_bps=0)
    payoff = (px[-1] - 100) * 100
    assert r["payoff_at_expiry"] == pytest.approx(payoff)
    assert r["final_pnl"] == pytest.approx(r["premium"] - payoff) and r["n_trades"] == 0
    assert r["rows"][0]["pnl"] == pytest.approx(0, abs=1e-9)   # 프리미엄 수취 직후 손익 0


def test_daily_hedge_reduces_pnl_swings_and_costs_more():
    ds = _dates(120)
    px = [100 * (1 + 0.001 * i + 0.02 * ((-1) ** i)) for i in range(120)]
    none = hedge_backtest(ds, px, 0.3, 0.02, rebalance_every=0, cost_bps=1)
    daily = hedge_backtest(ds, px, 0.3, 0.02, rebalance_every=1, cost_bps=1)
    weekly = hedge_backtest(ds, px, 0.3, 0.02, rebalance_every=5, cost_bps=1)
    assert daily["n_trades"] > weekly["n_trades"] > none["n_trades"] == 0
    assert daily["total_cost"] > weekly["total_cost"] > 0
    assert daily["rows"][-1]["shares"] == 0   # 만기에 주식 청산
