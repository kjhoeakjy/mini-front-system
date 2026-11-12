"""델타 헤지 제안과 단일 유럽형 콜 매도의 가상 재헤지 시뮬레이션. 실제 주문은 내지 않는다."""
from __future__ import annotations

import math
from datetime import date
from typing import Sequence

from ..domain.market import UNDERLYINGS
from .black_scholes import bsm


def delta_hedge(net_delta: dict, spots: dict, current_shares: dict, gamma: dict | None = None,
                integer_shares: bool = True, cost_bps: float = 1.0, fixed_fee: float = 0.0) -> dict:
    out = {}
    for u in UNDERLYINGS:
        d = net_delta[u]
        trade = -d
        if integer_shares:
            trade = float(round(trade))
        residual = d + trade
        notional = abs(trade) * spots[u]
        cost = notional * cost_bps / 10000.0 + (fixed_fee if trade != 0 else 0.0)
        g = (gamma or {}).get(u, 0.0)
        ds = 0.01 * spots[u]
        out[u] = {
            "net_delta_before": d, "trade_shares": trade, "side": "매수" if trade > 0 else "매도" if trade < 0 else "거래 없음",
            "shares_after": current_shares.get(u, 0.0) + trade, "net_delta_after": residual,
            "dollar_delta_before": d * spots[u], "dollar_delta_after": residual * spots[u],
            "trade_notional": notional, "estimated_cost": cost,
            "pnl_1pct_up_before": d * ds + 0.5 * g * ds * ds, "pnl_1pct_dn_before": -d * ds + 0.5 * g * ds * ds,
            "pnl_1pct_up_after": residual * ds + 0.5 * g * ds * ds, "pnl_1pct_dn_after": -residual * ds + 0.5 * g * ds * ds,
        }
    return out


def realized_vol(closes: Sequence[float]) -> float:
    r = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)


def hedge_backtest(dates: Sequence[date], prices: Sequence[float], sigma: float, r: float, q: float = 0.0,
                   rebalance_every: int = 1, cost_bps: float = 1.0, multiplier: int = 100, contracts: int = 1) -> dict:
    """콜 매도 후 주기적으로 델타만큼 주식을 보유한다.

    행사가는 시작일 종가, 만기는 종료일. 변동성과 금리는 기간 내 고정 가정이다.
    rebalance_every: 재헤지 간격(거래일). 0이면 헤지하지 않는다.
    현금계정: 프리미엄 유입, 주식 매매 대금, 거래 비용, 이자를 반영하고 만기에 지급액을 차감한다.
    """
    if len(dates) != len(prices) or len(dates) < 3:
        raise ValueError("가격 자료가 부족함")
    n_opt = multiplier * contracts
    K, expiry = prices[0], dates[-1]
    premium = bsm("CALL", prices[0], K, (expiry - dates[0]).days / 365.0, r, q, sigma).price * n_opt
    cash, shares, total_cost, n_trades = premium, 0.0, 0.0, 0
    rows = []
    for i, (d, s) in enumerate(zip(dates, prices)):
        if i > 0:
            cash *= math.exp(r * (d - dates[i - 1]).days / 365.0)
        T = (expiry - d).days / 365.0
        last = i == len(dates) - 1
        res = bsm("CALL", s, K, T, r, q, sigma)
        liability = res.price * n_opt
        if last:
            target = 0.0
        elif rebalance_every > 0 and i % rebalance_every == 0:
            target = float(round((res.delta or 0.0) * n_opt))
        else:
            target = shares
        trade = target - shares
        if trade != 0:
            c = abs(trade) * s * cost_bps / 10000.0
            cash -= trade * s + c
            total_cost += c; n_trades += 1; shares = target
        if last:
            cash -= liability   # 만기 지급
            liability = 0.0
        rows.append({"date": d.isoformat(), "spot": s, "option_value": res.price * n_opt if not last else max(s - K, 0.0) * n_opt,
                     "delta_per_share": res.delta, "shares": shares, "trade": trade, "cash": cash,
                     "pnl": cash + shares * s - liability})
    return {"strike": K, "premium": premium, "final_pnl": rows[-1]["pnl"], "total_cost": total_cost, "n_trades": n_trades,
            "payoff_at_expiry": max(prices[-1] - K, 0.0) * n_opt, "rows": rows,
            "assumptions": {"sigma": sigma, "r": r, "q": q, "rebalance_every": rebalance_every, "cost_bps": cost_bps}}
