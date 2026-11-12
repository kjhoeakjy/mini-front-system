"""유럽형 BSM 기준 내재변동성 역산 (이분법). 가격은 변동성의 단조증가함수이므로 해가 유일하다."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .black_scholes import bsm

SIGMA_LO, SIGMA_HI = 1e-6, 5.0


@dataclass(frozen=True)
class IvResult:
    implied_vol: Optional[float]
    status: str   # OK | BELOW_LOWER_BOUND | ABOVE_UPPER_BOUND | NO_ROOT_IN_BRACKET | INVALID_INPUT
    message: str
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


def no_arbitrage_bounds(option_type: str, S: float, K: float, T: float, r: float, q: float) -> tuple[float, float]:
    df_r, df_q = math.exp(-r * T), math.exp(-q * T)
    if option_type.upper() == "CALL":
        return max(S * df_q - K * df_r, 0.0), S * df_q
    return max(K * df_r - S * df_q, 0.0), K * df_r


def implied_volatility(market_price: float, option_type: str, S: float, K: float, T: float, r: float, q: float) -> IvResult:
    if not (market_price > 0 and S > 0 and K > 0 and T > 0):
        return IvResult(None, "INVALID_INPUT", "가격, 현물가, 행사가, 잔존만기는 0보다 커야 함")
    lo, hi = no_arbitrage_bounds(option_type, S, K, T, r, q)
    if market_price <= lo:
        return IvResult(None, "BELOW_LOWER_BOUND", "가격이 무차익 하한 이하임. 내재변동성 산출 불가", lo, hi)
    if market_price >= hi:
        return IvResult(None, "ABOVE_UPPER_BOUND", "가격이 무차익 상한 이상임. 내재변동성 산출 불가", lo, hi)

    def f(sig: float) -> float:
        return bsm(option_type, S, K, T, r, q, sig).price - market_price

    f_lo, f_hi = f(SIGMA_LO), f(SIGMA_HI)
    if f_lo * f_hi > 0:
        return IvResult(None, "NO_ROOT_IN_BRACKET", f"변동성 {SIGMA_LO}~{SIGMA_HI} 구간에 해가 없음", lo, hi)
    a, b = SIGMA_LO, SIGMA_HI
    for _ in range(200):
        mid = 0.5 * (a + b)
        if f(mid) > 0:
            b = mid
        else:
            a = mid
        if b - a < 1e-12:
            break
    iv = 0.5 * (a + b)
    return IvResult(float(iv), "OK", "유럽형 BSM 기준 역산값", lo, hi)
