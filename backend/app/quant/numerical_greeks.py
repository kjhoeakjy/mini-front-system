"""ELS 유사 노트의 유한차분 Greeks (공통 난수 사용).

모든 값은 투자자가 보유한 노트 1개 기준이다. 발행자(매도) 포지션은 부호가 반대다.
"""
from __future__ import annotations

from .autocallable_payoff import AutocallSpec
from .monte_carlo import McConfig, McMarket, Schedule, bumped, simulate

VOL_BUMP = 0.005     # 중앙차분: 양쪽 0.5%p, 합계 1%p
RATE_BUMP = 0.005    # 중앙차분: 양쪽 50bp, 합계 100bp
CORR_BUMP = 0.10
SPOT_BUMPS = (0.0025, 0.005, 0.01)
DEFAULT_SPOT_BUMP = 0.005


def els_price_and_greeks(spec: AutocallSpec, schedule: Schedule, market: McMarket, cfg: McConfig) -> dict:
    mk = [market]
    index = {}

    def add(name, m):
        index[name] = len(mk)
        mk.append(m)

    for b in SPOT_BUMPS:
        h1, h2 = max(market.s1 * b, 0.01), max(market.s2 * b, 0.01)
        add(("s1", b, +1), bumped(market, s1=market.s1 + h1)); add(("s1", b, -1), bumped(market, s1=market.s1 - h1))
        add(("s2", b, +1), bumped(market, s2=market.s2 + h2)); add(("s2", b, -1), bumped(market, s2=market.s2 - h2))
    v1, v2 = min(VOL_BUMP, market.sigma1 / 2), min(VOL_BUMP, market.sigma2 / 2)
    add("v1+", bumped(market, sigma1=market.sigma1 + v1)); add("v1-", bumped(market, sigma1=market.sigma1 - v1))
    add("v2+", bumped(market, sigma2=market.sigma2 + v2)); add("v2-", bumped(market, sigma2=market.sigma2 - v2))
    add("r+", bumped(market, r=market.r + RATE_BUMP)); add("r-", bumped(market, r=market.r - RATE_BUMP))
    add("c+", bumped(market, rho=min(market.rho + CORR_BUMP, 0.999))); add("c-", bumped(market, rho=max(market.rho - CORR_BUMP, -0.999)))
    res = simulate(spec, schedule, mk, cfg, detail_index=0)
    base = res[0]
    p = lambda name: res[index[name]].price

    def spot_greeks(key, s, b):
        h = max(s * b, 0.01)
        up, dn = p((key, b, +1)), p((key, b, -1))
        return (up - dn) / (2 * h), (up - 2 * base.price + dn) / (h * h)

    stability = []
    for b in SPOT_BUMPS:
        d1, g1 = spot_greeks("s1", market.s1, b)
        d2, g2 = spot_greeks("s2", market.s2, b)
        stability.append({"bump_pct": b * 100, "delta_1": d1, "delta_2": d2, "gamma_1": g1, "gamma_2": g2})
    d1, g1 = spot_greeks("s1", market.s1, DEFAULT_SPOT_BUMP)
    d2, g2 = spot_greeks("s2", market.s2, DEFAULT_SPOT_BUMP)
    greeks = {
        "delta_1": d1, "delta_2": d2,                  # 기초자산 $1 변화 시 노트 가치 변화(USD)
        "gamma_1": g1, "gamma_2": g2,                  # 기초자산 $1 변화 시 delta 변화
        "vega_1_per_1volpt": (p("v1+") - p("v1-")) / (2 * v1) * 0.01,
        "vega_2_per_1volpt": (p("v2+") - p("v2-")) / (2 * v2) * 0.01,
        "rho_per_100bp": (p("r+") - p("r-")) / (2 * RATE_BUMP) * 0.01,
        "theta_per_calendar_day": None,                # 발행 시점 평가 전용이므로 제공하지 않음
    }
    corr = {
        "bump": CORR_BUMP,
        "price_up": p("c+"), "price_down": p("c-"),
        "ki_rate_up": res[index["c+"]].knock_in_rate, "ki_rate_down": res[index["c-"]].knock_in_rate,
        "loss_rate_up": res[index["c+"]].loss_rate, "loss_rate_down": res[index["c-"]].loss_rate,
    }
    spread = [abs(s["delta_1"] - d1) / max(abs(d1), 1e-9) for s in stability] + [abs(s["delta_2"] - d2) / max(abs(d2), 1e-9) for s in stability]
    warnings = []
    if max(spread) > 0.15:
        warnings.append("현물 충격 폭에 따라 Delta 추정이 15% 이상 달라짐. 경로 수를 늘려 확인 필요")
    warnings.append("배리어에서 지급액이 불연속이므로 Gamma 추정의 잡음이 큼")
    return {"base": base, "greeks": greeks, "corr_sensitivity": corr, "bump_stability": stability,
            "bump_definition": {"spot_rel": DEFAULT_SPOT_BUMP, "vol_abs_each_side": VOL_BUMP, "rate_abs_each_side": RATE_BUMP},
            "warnings": warnings}
