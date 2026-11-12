from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..quant import example_paths
from ..quant.autocallable_payoff import AutocallSpec
from ..quant.monte_carlo import MODEL_VERSION, McConfig, McMarket, build_schedule, bumped, simulate
from ..quant.numerical_greeks import els_price_and_greeks
from ..services.valuation_service import mc_config
from ..storage.database import log_valuation

router = APIRouter(prefix="/structuring", tags=["structuring"])


class SpecIn(BaseModel):
    notional: float = 1000.0
    tenor_years: float = 2.0
    autocall_times: list = [0.5, 1.0, 1.5]
    autocall_barriers: list = [0.95, 0.90, 0.85]
    maturity_barrier: float = 0.80
    ki_barrier: float = 0.60
    coupon_rate: float = 0.10

    def to_spec(self) -> AutocallSpec:
        try:
            return AutocallSpec(notional=self.notional, tenor_years=self.tenor_years, autocall_times=tuple(self.autocall_times),
                                autocall_barriers=tuple(self.autocall_barriers), maturity_barrier=self.maturity_barrier,
                                ki_barrier=self.ki_barrier, coupon_rate=self.coupon_rate)
        except ValueError as e:
            raise HTTPException(422, str(e))


class MarketIn(BaseModel):
    spot_1: float
    spot_2: float
    ref_1: Optional[float] = None   # 생략 시 현물가를 기준가로 사용(신규 발행)
    ref_2: Optional[float] = None
    vol_1: float
    vol_2: float
    div_1: float
    div_2: float
    rate: float
    corr: float

    def to_market(self) -> McMarket:
        m = McMarket(self.spot_1, self.spot_2, self.ref_1 or self.spot_1, self.ref_2 or self.spot_2,
                     self.vol_1, self.vol_2, self.div_1, self.div_2, self.rate, self.corr)
        try:
            m.validate()
        except ValueError as e:
            raise HTTPException(422, str(e))
        return m


class PayoffIn(BaseModel):
    spec: SpecIn = SpecIn()
    scenario_id: Optional[str] = None
    points: Optional[list] = None   # [[연, worst 비율], ...]


@router.post("/payoff")
def payoff(b: PayoffIn):
    spec = b.spec.to_spec()
    ex = example_paths.examples(spec)
    if b.points is None and b.scenario_id is None:
        return {"examples": [{**e, "result": example_paths.evaluate(spec, e["points"])} for e in ex], "label": "MANUAL SCENARIO",
                "note": "꺾은선으로 만든 가상 경로. 지급액은 계약 지급 함수의 계산 결과"}
    if b.points is None:
        found = [e for e in ex if e["id"] == b.scenario_id]
        if not found:
            raise HTTPException(404, "시나리오 없음")
        pts = found[0]["points"]
    else:
        pts = b.points
    try:
        return {"result": example_paths.evaluate(spec, pts), "label": "MANUAL SCENARIO"}
    except ValueError as e:
        raise HTTPException(422, str(e))


class PriceIn(BaseModel):
    spec: SpecIn = SpecIn()
    market: MarketIn
    issue_date: Optional[date] = None
    n_paths: int = 20000
    seed: int = 42
    signed_quantity: float = -10
    input_mode: str = "MANUAL SCENARIO"


@router.post("/price")
def price(b: PriceIn):
    spec, mk, cfg = b.spec.to_spec(), b.market.to_market(), mc_config(b.n_paths, b.seed)
    sch = build_schedule(spec, b.issue_date)
    out = els_price_and_greeks(spec, sch, mk, cfg)
    base, g = out["base"], out["greeks"]
    shocks = simulate(spec, sch, [mk, bumped(mk, s1=mk.s1 * 0.9, s2=mk.s2 * 0.9), bumped(mk, s1=mk.s1 * 1.1, s2=mk.s2 * 1.1)], cfg, detail_index=None)
    q = b.signed_quantity
    res = {
        "model": "MC_GBM_2ASSET", "model_version": MODEL_VERSION, "input_mode": b.input_mode, "result_label": "MODEL ESTIMATE",
        "n_paths": base.n_paths, "seed": cfg.seed, "antithetic": cfg.antithetic,
        "schedule": {"observation_dates": [d.isoformat() for d in sch.dates], "discount_year_fractions": list(sch.pay_times),
                     "coupon_year_fractions": list(spec.autocall_times) + [spec.tenor_years], "step_index": list(sch.obs_idx) + [sch.maturity_idx],
                     "rule": "발행일에 6·12·18·24개월을 더한 뒤 주말이면 수정후영업일 규칙으로 조정. 쿠폰은 계약상 연수, 할인은 실제 일수/365"},
        "investor": {"price_per_note": base.price, "std_error": base.std_error, "ci95": [base.ci_low, base.ci_high]},
        "issue_price": spec.notional, "issuer_margin_per_note": spec.notional - base.price,
        "margin_note": "발행가와 이론가의 차이. 헤지 비용, 조달 비용, 신용위험은 반영하지 않음",
        "issuer_position": {"signed_quantity": q, "mtm": base.price * q,
                            "delta_shares": {"1": g["delta_1"] * q, "2": g["delta_2"] * q},
                            "hedge_shares": {"1": -g["delta_1"] * q, "2": -g["delta_2"] * q}},
        "distribution": {"category_fraction": base.category_fraction, "fraction_sum": sum(base.category_fraction.values()),
                         "knock_in_rate": base.knock_in_rate, "loss_rate": base.loss_rate, "avg_redeem_time": base.avg_redeem_time,
                         "min_payoff_in_sample": base.min_payoff, "mean_payoff_undiscounted": base.mean_payoff,
                         "final_worst_hist": base.final_worst_hist,
                         "note": "위험중립 모형 아래의 경로 빈도. 실제 발생 확률이 아님"},
        "greeks_investor_per_note": g, "corr_sensitivity": out["corr_sensitivity"], "bump_stability": out["bump_stability"],
        "bump_definition": out["bump_definition"],
        "spot_shock": {"down_10pct": {"price": shocks[1].price, "change": shocks[1].price - shocks[0].price},
                       "up_10pct": {"price": shocks[2].price, "change": shocks[2].price - shocks[0].price},
                       "note": "기준가는 고정하고 현재 평가용 현물가를 이동"},
        "sample_paths": base.sample_paths,
        "warnings": out["warnings"] + ["평탄 변동성·고정 상관계수 GBM 가정", "낙인은 시뮬레이션 일별 종가 기준 관측", "Theta는 발행 시점 평가 전용 범위에서 제공하지 않음"],
    }
    res["valuation_id"] = log_valuation("structuring", b.model_dump(mode="json"), {k: v for k, v in res.items() if k != "sample_paths"},
                                        model_version=MODEL_VERSION, seed=cfg.seed, n_paths=cfg.n_paths, warnings=res["warnings"])
    return res


class ConvIn(BaseModel):
    spec: SpecIn = SpecIn()
    market: MarketIn
    seed: int = 42
    path_counts: list = [1000, 2000, 5000, 10000, 20000, 50000]


@router.post("/convergence")
def convergence(b: ConvIn):
    spec, mk = b.spec.to_spec(), b.market.to_market()
    sch = build_schedule(spec)
    rows = []
    for n in b.path_counts[:8]:
        r = simulate(spec, sch, [mk], McConfig(n_paths=int(n), seed=b.seed), detail_index=None)[0]
        rows.append({"n_paths": r.n_paths, "price": r.price, "std_error": r.std_error, "ci_low": r.ci_low, "ci_high": r.ci_high})
    return {"rows": rows, "note": "경로 수가 늘면 표준오차는 대체로 1/√n 비율로 줄어듦. 특정 시드에서 단조 감소를 보장하지 않음"}
