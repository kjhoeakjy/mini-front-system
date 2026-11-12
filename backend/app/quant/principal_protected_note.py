"""원금지급형 주가연계 채권(1자산, 유럽형 지급). 할인채와 콜옵션의 합으로 복제해 평가한다.

만기 지급액(투자자) = N + alpha * N * max(S_T / S0 - 1, 0)
이론가 V0 = N * exp(-rT) + (alpha * N / S0) * C_BSM(S, K=S0, T, r, q, sigma)

발행사 신용위험과 조달·헤지·판매 비용은 반영하지 않는다. alpha는 소수(50% = 0.5)이다.
"""
from __future__ import annotations

import math

import numpy as np

from .black_scholes import bsm

MODEL_VERSION = "ppn-v1"


def _check(N: float, alpha: float, S0: float):
    if not (N > 0 and S0 > 0):
        raise ValueError("표시원금과 기준가는 0보다 커야 함")
    if not (0 <= alpha <= 5):
        raise ValueError("참여율은 0~5(0%~500%) 범위의 소수여야 함")


def payoff(N: float, alpha: float, S0: float, ST: float) -> float:
    _check(N, alpha, S0)
    return N + alpha * N * max(ST / S0 - 1.0, 0.0)


def price(N: float, alpha: float, S0: float, S: float, T: float, r: float, q: float, sigma: float) -> dict:
    """투자자 보유 1개 기준 이론가와 Greeks. 단위는 옵션 화면과 동일하다."""
    _check(N, alpha, S0)
    if T <= 0:
        raise ValueError("잔존만기는 0보다 커야 함")
    call = bsm("CALL", S, S0, T, r, q, sigma)
    units = alpha * N / S0                    # 콜옵션 보유 수량(주 환산)
    bond = N * math.exp(-r * T)
    opt = units * call.price
    return {
        "bond_value": bond, "option_value": opt, "price": bond + opt, "call_per_share": call.price, "call_units": units,
        "greeks": {
            "delta_shares": units * call.delta,
            "gamma_per_usd": units * call.gamma,
            "vega_per_1volpt_usd": units * call.vega_raw * 0.01,
            "theta_per_calendar_day_usd": (r * bond + units * call.theta_annual) / 365.0,
            "rho_per_100bp_usd": (-T * bond + units * call.rho_raw) * 0.01,
        },
    }


def solve_participation(target: float, N: float, S0: float, S: float, T: float, r: float, q: float, sigma: float) -> float | None:
    """이론가가 target이 되는 참여율. 할인채 가치가 target 이상이면 None."""
    _check(N, 0.0, S0)
    bond = N * math.exp(-r * T)
    unit_opt = N / S0 * bsm("CALL", S, S0, T, r, q, sigma).price
    if target <= bond or unit_opt <= 0:
        return None
    return (target - bond) / unit_opt


def mc_price(N: float, alpha: float, S0: float, S: float, T: float, r: float, q: float, sigma: float,
             n_paths: int = 200000, seed: int = 42) -> dict:
    """위험중립 측도의 만기 주가를 직접 추출한 Monte Carlo 대조 가격(대조변수법)."""
    _check(N, alpha, S0)
    half = max(n_paths // 2, 1)
    z = np.random.default_rng(seed).standard_normal(half)
    drift, vol = (r - q - 0.5 * sigma * sigma) * T, sigma * math.sqrt(T)
    df = math.exp(-r * T)

    def pv(zz):
        st = S * np.exp(drift + vol * zz)
        return df * (N + alpha * N * np.maximum(st / S0 - 1.0, 0.0))

    pair = 0.5 * (pv(z) + pv(-z))
    return {"price": float(pair.mean()), "std_error": float(pair.std(ddof=1) / math.sqrt(half)), "n_paths": 2 * half, "seed": seed}
