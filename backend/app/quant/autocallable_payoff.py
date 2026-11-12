"""Worst-of 스텝다운 조기상환형 노트(ELS 유사)의 계약상 지급 규칙.

난수와 무관한 순수 함수다. payoff_path()는 경로 하나를 순서대로 읽는 구현이고
payoff_vectorized()는 Monte Carlo용 배열 구현이다. 두 구현의 일치는 테스트로 검증한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

CAT_MATURITY_COUPON = "MATURITY_ABOVE_BARRIER"   # 만기 W >= 만기 배리어
CAT_MATURITY_NO_KI = "MATURITY_NO_KNOCK_IN"      # 만기 W < 만기 배리어, 낙인 없음
CAT_MATURITY_LOSS = "MATURITY_LOSS"              # 낙인 발생 후 만기 W < 만기 배리어


@dataclass(frozen=True)
class AutocallSpec:
    product_id: str = "ELS-DEMO-SPY-QQQ-001"
    underlyings: tuple = ("SPY", "QQQ")
    notional: float = 1000.0
    tenor_years: float = 2.0
    autocall_times: tuple = (0.5, 1.0, 1.5)        # 계약상 관측 시점(연)
    autocall_barriers: tuple = (0.95, 0.90, 0.85)  # 기준가 대비 비율
    maturity_barrier: float = 0.80
    ki_barrier: float = 0.60
    coupon_rate: float = 0.10                       # 연 단리, 중간 지급 없음

    def __post_init__(self):
        if len(self.autocall_times) != len(self.autocall_barriers):
            raise ValueError("조기상환 시점과 배리어의 개수가 다름")
        ts = list(self.autocall_times) + [self.tenor_years]
        if any(b <= a for a, b in zip(ts, ts[1:])) or ts[0] <= 0:
            raise ValueError("관측 시점은 0보다 크고 만기 이전에서 증가해야 함")
        if not (0 < self.ki_barrier and self.notional > 0):
            raise ValueError("낙인 배리어와 원금은 0보다 커야 함")

    @property
    def categories(self) -> list:
        return [f"AUTOCALL_{i + 1}" for i in range(len(self.autocall_times))] + [
            CAT_MATURITY_COUPON, CAT_MATURITY_NO_KI, CAT_MATURITY_LOSS]


@dataclass(frozen=True)
class PayoffResult:
    amount: float          # 투자자 수령액 (노트 1개당, USD)
    redeem_time: float     # 계약상 상환 시점(연)
    redeem_slot: int       # 0..n-1 조기상환 회차, n = 만기
    category: str
    knocked_in: bool
    worst_at_redeem: float
    steps: list = field(default_factory=list)  # 판정 과정 설명


def payoff_path(spec: AutocallSpec, ratio1: Sequence[float], ratio2: Sequence[float],
                obs_idx: Sequence[int], maturity_idx: int) -> PayoffResult:
    """경로 하나의 지급액.

    ratio1, ratio2: 기준가 대비 일별 종가 비율. 인덱스 0은 평가 시점.
    obs_idx: 조기상환 관측일의 인덱스, maturity_idx: 만기 관측일의 인덱스.
    """
    r1, r2 = np.asarray(ratio1, float), np.asarray(ratio2, float)
    if len(r1) != len(r2) or maturity_idx >= len(r1):
        raise ValueError("경로 길이가 만기 인덱스보다 짧거나 두 자산의 길이가 다름")
    worst = np.minimum(r1, r2)
    steps = []
    n = len(spec.autocall_times)
    for k in range(n):
        w = float(worst[obs_idx[k]])
        ok = w >= spec.autocall_barriers[k]
        steps.append(f"{spec.autocall_times[k]}년 관측: W={w:.4f}, 배리어 {spec.autocall_barriers[k]:.2f}, {'조기상환' if ok else '미충족'}")
        if ok:
            ki = bool(np.min(worst[: obs_idx[k] + 1]) <= spec.ki_barrier)
            amt = spec.notional * (1.0 + spec.coupon_rate * spec.autocall_times[k])
            return PayoffResult(amt, spec.autocall_times[k], k, f"AUTOCALL_{k + 1}", ki, w, steps)
    w_final = float(worst[maturity_idx])
    knocked_in = bool(np.min(worst[: maturity_idx + 1]) <= spec.ki_barrier)
    full = spec.notional * (1.0 + spec.coupon_rate * spec.tenor_years)
    if w_final >= spec.maturity_barrier:
        cat, amt = CAT_MATURITY_COUPON, full
    elif not knocked_in:
        cat, amt = CAT_MATURITY_NO_KI, full
    else:
        cat, amt = CAT_MATURITY_LOSS, spec.notional * w_final
    steps.append(f"만기 관측: W={w_final:.4f}, 만기 배리어 {spec.maturity_barrier:.2f}, 낙인 {'발생' if knocked_in else '없음'}")
    return PayoffResult(amt, spec.tenor_years, n, cat, knocked_in, w_final, steps)


def payoff_vectorized(spec: AutocallSpec, w_obs: np.ndarray, w_final: np.ndarray, w_min: np.ndarray):
    """여러 경로의 지급액.

    w_obs: (경로 수, 조기상환 횟수) 관측일의 worst 비율
    w_final: 만기일 worst 비율, w_min: 평가 시점부터 만기까지 일별 worst 비율의 최솟값
    반환: (지급액, 상환 회차, 범주 코드) - 범주 코드는 spec.categories의 인덱스
    """
    n = len(spec.autocall_times)
    hit = w_obs >= np.asarray(spec.autocall_barriers)[None, :]
    called = hit.any(axis=1)
    first = np.where(called, hit.argmax(axis=1), n)
    coupons = np.asarray(list(spec.autocall_times) + [spec.tenor_years])
    amount = spec.notional * (1.0 + spec.coupon_rate * coupons[first])
    category = first.copy()
    at_mat = ~called
    knocked = w_min <= spec.ki_barrier
    below = w_final < spec.maturity_barrier
    no_ki = at_mat & below & ~knocked
    loss = at_mat & below & knocked
    category[no_ki] = n + 1
    category[loss] = n + 2
    amount = np.where(loss, spec.notional * w_final, amount)
    return amount, first, category
