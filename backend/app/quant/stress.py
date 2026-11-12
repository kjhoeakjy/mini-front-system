"""시나리오 분석: 충격 후 평가금액 - 기준 평가금액. VaR나 손실 확률 예측이 아니다."""
from __future__ import annotations

from typing import Sequence

from ..domain.market import UNDERLYINGS, MarketInputs
from .monte_carlo import McConfig
from .portfolio_risk import reprice

PRESETS = [
    {"id": "spy_dn5", "name": "SPY -5%", "spot_pct": {"SPY": -5}},
    {"id": "qqq_dn5", "name": "QQQ -5%", "spot_pct": {"QQQ": -5}},
    {"id": "both_dn10", "name": "SPY·QQQ -10%", "spot_pct": {"SPY": -10, "QQQ": -10}},
    {"id": "both_up10", "name": "SPY·QQQ +10%", "spot_pct": {"SPY": 10, "QQQ": 10}},
    {"id": "vol_up5", "name": "변동성 +5%p", "vol_pts": 5},
    {"id": "vol_dn5", "name": "변동성 -5%p", "vol_pts": -5},
    {"id": "rate_up100", "name": "금리 +100bp", "rate_bp": 100},
    {"id": "corr_up", "name": "상관계수 +0.10", "corr_shift": 0.10},
    {"id": "corr_dn", "name": "상관계수 -0.10", "corr_shift": -0.10},
]


def greek_approx(totals: dict, base: MarketInputs, sc: dict) -> dict:
    """기준 시점 Greeks로 추정한 손익. 교차 감마와 상관계수 효과는 포함하지 않는다."""
    d = g = 0.0
    for u in UNDERLYINGS:
        ds = base.spots[u] * sc.get("spot_pct", {}).get(u, 0.0) / 100.0
        d += totals["delta"][u] * ds
        g += 0.5 * totals["gamma"][u] * ds * ds
    v = sum(totals["vega"][u] for u in UNDERLYINGS) * sc.get("vol_pts", 0.0)
    r = totals["rho"] * sc.get("rate_bp", 0.0) / 100.0
    return {"delta": d, "gamma": g, "vega": v, "rho": r, "delta_only": d, "delta_gamma": d + g, "all_greeks": d + g + v + r}


def run_scenarios(positions: Sequence[dict], base: MarketInputs, scenarios: Sequence[dict], cfg: McConfig,
                  totals: dict | None = None) -> dict:
    shocked, warns = [], []
    for sc in scenarios:
        inp, w = base.shocked(sc.get("spot_pct"), sc.get("vol_pts", 0.0), sc.get("rate_bp", 0.0), sc.get("corr_shift", 0.0))
        shocked.append(inp); warns.append(w)
    vals = reprice(positions, [base] + shocked, cfg)
    b = vals[0]
    noise = 1.96 * sum(b["mc_std_error"])
    out = []
    for sc, v, w in zip(scenarios, vals[1:], warns):
        pnl = v["total"] - b["total"]
        row = {"id": sc.get("id", "custom"), "name": sc.get("name", "사용자 정의"), "shock": {k: sc[k] for k in ("spot_pct", "vol_pts", "rate_bp", "corr_shift") if k in sc},
               "base_value": b["total"], "shocked_value": v["total"], "pnl_full_reprice": pnl,
               "by_position": [sv - bv for sv, bv in zip(v["values"], b["values"])], "warnings": list(w)}
        if totals is not None:
            row["approx"] = greek_approx(totals, base, sc)
        out.append(row)
    return {"base_total": b["total"], "base_by_position": b["values"], "scenarios": out, "mc_noise_95": noise,
            "note": "노트는 기준과 충격을 같은 난수로 평가함. 평가금액 수준의 95% 오차 한계는 mc_noise_95이며 손익 차이의 잡음은 이보다 작음"}
