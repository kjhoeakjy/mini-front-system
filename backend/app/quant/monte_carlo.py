"""위험중립 2자산 GBM Monte Carlo.

하나의 난수 집합으로 여러 시장 조건을 동시에 평가한다(공통 난수, CRN).
기준 평가와 충격 평가의 차이에서 시뮬레이션 잡음을 줄이기 위함이다.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Optional, Sequence

import numpy as np

from .autocallable_payoff import AutocallSpec, payoff_vectorized

MODEL_VERSION = "mc-gbm2-v1"
STEPS_PER_YEAR = 252


@dataclass(frozen=True)
class McMarket:
    s1: float            # 현재 평가용 현물가
    s2: float
    s1_ref: float        # 발행 기준가 (충격을 주어도 변하지 않음)
    s2_ref: float
    sigma1: float
    sigma2: float
    q1: float
    q2: float
    r: float
    rho: float

    def validate(self):
        if min(self.s1, self.s2, self.s1_ref, self.s2_ref) <= 0:
            raise ValueError("현물가와 기준가는 0보다 커야 함")
        if min(self.sigma1, self.sigma2) <= 0:
            raise ValueError("변동성은 0보다 커야 함")
        if not (-0.999 <= self.rho <= 0.999):
            raise ValueError("상관계수는 -0.999~0.999 범위여야 함")


@dataclass(frozen=True)
class McConfig:
    n_paths: int = 20000
    seed: int = 42
    antithetic: bool = True
    chunk_pairs: int = 2500
    n_sample_paths: int = 40


@dataclass(frozen=True)
class Schedule:
    obs_idx: tuple          # 조기상환 관측일의 시뮬레이션 스텝 번호 (1부터)
    maturity_idx: int
    pay_times: tuple        # 할인에 쓰는 실제 연수 (조기상환 회차들 + 만기)
    dates: tuple = ()       # 실제 관측 날짜 (있을 때만)


def _add_months(d: date, months: int) -> date:
    y, m = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def modified_following(d: date) -> date:
    """주말이면 다음 평일로 미루되 달이 바뀌면 이전 평일로 당긴다. 거래소 휴장일은 반영하지 않는다."""
    x = d
    while x.weekday() >= 5:
        x += timedelta(days=1)
    if x.month != d.month:
        x = d
        while x.weekday() >= 5:
            x -= timedelta(days=1)
    return x


def build_schedule(spec: AutocallSpec, issue_date: Optional[date] = None) -> Schedule:
    times = list(spec.autocall_times) + [spec.tenor_years]
    if issue_date is None:
        taus, dates = times, ()
    else:
        ds = [modified_following(_add_months(issue_date, int(round(t * 12)))) for t in times]
        taus, dates = [(d - issue_date).days / 365.0 for d in ds], tuple(ds)
    idx = [max(1, int(round(t * STEPS_PER_YEAR))) for t in taus]
    if any(b <= a for a, b in zip(idx, idx[1:])):
        raise ValueError("관측 시점 간격이 너무 좁음")
    return Schedule(tuple(idx[:-1]), idx[-1], tuple(taus), dates)


@dataclass
class McResult:
    price: float                 # 투자자 보유 노트 1개의 이론가
    std_error: float
    ci_low: float
    ci_high: float
    n_paths: int
    category_fraction: dict      # 상호 배타 범주별 경로 비율 (합 1)
    knock_in_rate: float         # 상환 전 낙인을 경험한 경로 비율
    loss_rate: float             # 원금 손실 상환 비율
    avg_redeem_time: float
    min_payoff: float
    mean_payoff: float
    final_worst_hist: Optional[dict] = None
    sample_paths: Optional[dict] = None


def simulate(spec: AutocallSpec, schedule: Schedule, markets: Sequence[McMarket], cfg: McConfig,
             detail_index: Optional[int] = 0) -> list:
    """동일 난수로 markets의 각 조건을 평가한다. detail_index의 조건에만 분포·표본 경로를 붙인다."""
    for m in markets:
        m.validate()
    if cfg.n_paths < 2:
        raise ValueError("경로 수는 2 이상이어야 함")
    n_pairs = cfg.n_paths // 2 if cfg.antithetic else cfg.n_paths
    signs = (1.0, -1.0) if cfg.antithetic else (1.0,)
    steps = schedule.maturity_idx
    dt = 1.0 / STEPS_PER_YEAR
    t = np.arange(1, steps + 1) * dt
    obs = np.asarray(schedule.obs_idx) - 1
    n_cat = len(spec.categories)
    rng = np.random.default_rng(cfg.seed)
    K = len(markets)
    sum_u, sum_u2 = np.zeros(K), np.zeros(K)
    cat_count = np.zeros((K, n_cat))
    ki_count, redeem_sum, pay_sum = np.zeros(K), np.zeros(K), np.zeros(K)
    min_pay = np.full(K, np.inf)
    bins = np.linspace(0.0, 1.6, 33)
    hist = np.zeros(len(bins) - 1)
    sample = None
    nominal_times = np.asarray(list(spec.autocall_times) + [spec.tenor_years])
    pay_times = np.asarray(schedule.pay_times)
    done = 0
    while done < n_pairs:
        m = min(cfg.chunk_pairs, n_pairs - done)
        z = rng.standard_normal((m, 2, steps))   # 경로 단위로 순서대로 뽑아 묶음 크기와 무관하게 동일한 난수를 쓴다
        w1 = np.cumsum(z[:, 0, :], axis=1) * math.sqrt(dt)
        wp = np.cumsum(z[:, 1, :], axis=1) * math.sqrt(dt)
        del z
        for k, mk in enumerate(markets):
            x1_0, x2_0 = math.log(mk.s1 / mk.s1_ref), math.log(mk.s2 / mk.s2_ref)
            mu1 = (mk.r - mk.q1 - 0.5 * mk.sigma1 ** 2) * t
            mu2 = (mk.r - mk.q2 - 0.5 * mk.sigma2 ** 2) * t
            b2 = mk.rho * w1 + math.sqrt(1.0 - mk.rho ** 2) * wp
            disc = np.exp(-mk.r * pay_times)
            pair_pv = np.zeros(m)
            for sg in signs:
                x1 = x1_0 + mu1 + (sg * mk.sigma1) * w1
                x2 = x2_0 + mu2 + (sg * mk.sigma2) * b2
                lw = np.minimum(x1, x2)
                w_obs, w_fin = np.exp(lw[:, obs]), np.exp(lw[:, -1])
                w_min = np.exp(np.minimum(lw.min(axis=1), min(x1_0, x2_0)))
                amount, slot, cat = payoff_vectorized(spec, w_obs, w_fin, w_min)
                pair_pv += amount * disc[slot]
                cat_count[k] += np.bincount(cat, minlength=n_cat)
                # 상환 시점까지의 낙인 경험 여부
                run_min = np.minimum.accumulate(lw, axis=1)
                idx_redeem = np.where(slot < len(obs), obs[np.minimum(slot, len(obs) - 1)], steps - 1)
                ki_before = np.exp(np.minimum(run_min[np.arange(m), idx_redeem], min(x1_0, x2_0))) <= spec.ki_barrier
                ki_count[k] += ki_before.sum()
                redeem_sum[k] += nominal_times[slot].sum()
                pay_sum[k] += amount.sum()
                min_pay[k] = min(min_pay[k], float(amount.min()))
                if detail_index is not None and k == detail_index:
                    hist += np.histogram(w_fin[slot == len(obs)], bins=bins)[0]
                    if sample is None and sg == 1.0:
                        ns = min(cfg.n_sample_paths, m)
                        sel = np.arange(0, steps, 5)
                        if sel[-1] != steps - 1:
                            sel = np.append(sel, steps - 1)
                        sample = {
                            "t": [0.0] + [round(float(v), 4) for v in t[sel]],
                            "ratio1": [[round(math.exp(x1_0), 4)] + [round(float(v), 4) for v in np.exp(x1[i, sel])] for i in range(ns)],
                            "ratio2": [[round(math.exp(x2_0), 4)] + [round(float(v), 4) for v in np.exp(x2[i, sel])] for i in range(ns)],
                            "category": [spec.categories[int(c)] for c in cat[:ns]],
                            "redeem_time": [float(v) for v in nominal_times[slot[:ns]]],
                        }
            u = pair_pv / len(signs)
            sum_u[k] += u.sum()
            sum_u2[k] += (u * u).sum()
        done += m
    total = n_pairs * len(signs)
    out = []
    for k in range(K):
        mean = sum_u[k] / n_pairs
        var = max(sum_u2[k] / n_pairs - mean * mean, 0.0) * n_pairs / (n_pairs - 1)
        se = math.sqrt(var / n_pairs)   # 대조 변수 사용 시 경로쌍 평균의 표준오차
        frac = {c: float(cat_count[k, i] / total) for i, c in enumerate(spec.categories)}
        res = McResult(
            price=float(mean), std_error=float(se), ci_low=float(mean - 1.96 * se), ci_high=float(mean + 1.96 * se),
            n_paths=int(total), category_fraction=frac, knock_in_rate=float(ki_count[k] / total),
            loss_rate=frac["MATURITY_LOSS"], avg_redeem_time=float(redeem_sum[k] / total),
            min_payoff=float(min_pay[k]), mean_payoff=float(pay_sum[k] / total))
        if detail_index is not None and k == detail_index:
            res.final_worst_hist = {"bin_edges": [round(float(b), 3) for b in bins], "count": [int(c) for c in hist]}
            res.sample_paths = sample
        out.append(res)
    return out


def bumped(m: McMarket, **kw) -> McMarket:
    return replace(m, **kw)


def mc_european_call(S: float, K: float, T: float, r: float, q: float, sigma: float, n_paths: int, seed: int):
    """엔진 검증용: 1자산 유럽형 콜을 같은 방식(GBM, 대조 변수)으로 평가한다."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n_paths // 2)
    pv = []
    for sg in (1.0, -1.0):
        st = S * np.exp((r - q - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * sg * z)
        pv.append(np.exp(-r * T) * np.maximum(st - K, 0.0))
    u = 0.5 * (pv[0] + pv[1])
    return float(u.mean()), float(u.std(ddof=1) / math.sqrt(len(u)))
