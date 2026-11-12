"""배당을 포함한 Black-Scholes-Merton 유럽형 옵션 가격과 Greeks.

모든 값은 주당(per-share) 기준이며 금리·배당·변동성은 연율 소수(4% = 0.04)이다.
포지션 단위 환산은 position_greeks()에서 수행한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


MODEL_VERSION = "bsm-v1"
_SQRT2, _INV_SQRT_2PI = math.sqrt(2.0), 1.0 / math.sqrt(2.0 * math.pi)


def norm_cdf(x: float) -> float:
    """표준정규 누적분포함수."""
    return 0.5 * math.erfc(-x / _SQRT2)


def norm_pdf(x: float) -> float:
    """표준정규 확률밀도함수."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


@dataclass(frozen=True)
class BsmResult:
    price: float
    delta: Optional[float]
    gamma: Optional[float]
    vega_raw: Optional[float]      # sigma가 1.0(=100%p) 변할 때 주당 가격 변화
    theta_annual: Optional[float]  # 1년 경과 기준 주당 가격 변화
    rho_raw: Optional[float]       # r이 1.0(=100%p) 변할 때 주당 가격 변화
    d1: Optional[float]
    d2: Optional[float]
    note: str = ""


def _check(option_type: str, S: float, K: float) -> str:
    ot = option_type.upper()
    if ot not in ("CALL", "PUT"):
        raise ValueError("option_type은 CALL 또는 PUT이어야 함")
    if not (S > 0 and K > 0):
        raise ValueError("spot과 strike는 0보다 커야 함")
    return ot


def bsm(option_type: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> BsmResult:
    ot = _check(option_type, S, K)
    if sigma < 0:
        raise ValueError("변동성은 음수일 수 없음")
    if T <= 0:
        # 만기 도래: 지급액 그대로. Greeks는 정의되지 않음.
        intrinsic = max(S - K, 0.0) if ot == "CALL" else max(K - S, 0.0)
        return BsmResult(intrinsic, None, None, None, None, None, None, None, "만기 도래: 지급액으로 평가, Greeks 미정의")
    df_r, df_q = math.exp(-r * T), math.exp(-q * T)
    if sigma == 0:
        # 변동성 0: 선도가격이 확정되므로 할인된 지급액으로 평가.
        fwd = S * math.exp((r - q) * T)
        if ot == "CALL":
            price, itm = df_r * max(fwd - K, 0.0), fwd > K
            delta = df_q if itm else 0.0
            rho = K * T * df_r if itm else 0.0
            theta = (q * S * df_q - r * K * df_r) if itm else 0.0
        else:
            price, itm = df_r * max(K - fwd, 0.0), fwd < K
            delta = -df_q if itm else 0.0
            rho = -K * T * df_r if itm else 0.0
            theta = (r * K * df_r - q * S * df_q) if itm else 0.0
        return BsmResult(price, delta, 0.0, 0.0, theta, rho, None, None, "변동성 0: 확정 선도가격 기준 평가")
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / sq
    d2 = d1 - sq
    pdf = norm_pdf(d1)
    gamma = df_q * pdf / (S * sq)
    vega = S * df_q * pdf * math.sqrt(T)
    decay = -S * df_q * pdf * sigma / (2.0 * math.sqrt(T))
    if ot == "CALL":
        price = S * df_q * norm_cdf(d1) - K * df_r * norm_cdf(d2)
        delta = df_q * norm_cdf(d1)
        theta = decay - r * K * df_r * norm_cdf(d2) + q * S * df_q * norm_cdf(d1)
        rho = K * T * df_r * norm_cdf(d2)
    else:
        price = K * df_r * norm_cdf(-d2) - S * df_q * norm_cdf(-d1)
        delta = df_q * (norm_cdf(d1) - 1.0)
        theta = decay + r * K * df_r * norm_cdf(-d2) - q * S * df_q * norm_cdf(-d1)
        rho = -K * T * df_r * norm_cdf(-d2)
    return BsmResult(price, delta, gamma, vega, theta, rho, d1, d2)


def position_greeks(res: BsmResult, multiplier: float, signed_quantity: float) -> dict:
    """포지션 단위 Greeks. 단위는 화면 정의와 동일하다."""
    scale = multiplier * signed_quantity

    def s(x: Optional[float], k: float = 1.0) -> Optional[float]:
        return None if x is None else x * k * scale

    return {
        "delta_shares": s(res.delta),                       # 기초자산 $1 변화 시 USD 변화 = 헤지 주식 수
        "gamma_per_usd": s(res.gamma),                      # 기초자산 $1 변화 시 delta 변화
        "vega_per_1volpt_usd": s(res.vega_raw, 0.01),       # 변동성 +1%p
        "theta_per_calendar_day_usd": s(res.theta_annual, 1.0 / 365.0),  # 1일 경과
        "rho_per_100bp_usd": s(res.rho_raw, 0.01),          # 금리 +100bp
    }


def year_fraction(valuation_date, expiry) -> float:
    return (expiry - valuation_date).days / 365.0
