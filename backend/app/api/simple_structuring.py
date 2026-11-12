from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..quant import principal_protected_note as ppn
from ..storage.database import log_valuation

router = APIRouter(prefix="/simple-structuring", tags=["simple-structuring"])


class NoteIn(BaseModel):
    notional: float = 1000.0
    participation: float = 0.5        # 소수. 50% = 0.5
    reference_level: float            # 기준가 S0 (계약 조건, 고정)
    spot: float
    tenor_years: float = 1.0
    risk_free_rate: float
    dividend_yield: float
    volatility: float
    issue_price: Optional[float] = 1000.0
    mc_check: bool = False
    n_paths: int = 200000
    seed: int = 42


@router.post("/price")
def price(b: NoteIn):
    """원금지급형 주가연계 채권의 이론가(투자자 보유 1개). 발행사 신용위험·비용 미반영."""
    a = (b.notional, b.participation, b.reference_level, b.spot, b.tenor_years, b.risk_free_rate, b.dividend_yield, b.volatility)
    try:
        out = ppn.price(*a)
        out["payoff_curve"] = [{"ratio": 0.6 + 0.02 * i, "spot_at_maturity": b.reference_level * (0.6 + 0.02 * i),
                                "payoff": ppn.payoff(b.notional, b.participation, b.reference_level, b.reference_level * (0.6 + 0.02 * i))}
                               for i in range(41)]
        out["examples"] = [{"ratio": x, "payoff": ppn.payoff(b.notional, b.participation, b.reference_level, b.reference_level * x)}
                           for x in (0.8, 1.0, 1.2)]
        if b.issue_price:
            out["issue_price"] = b.issue_price
            out["issue_minus_model"] = b.issue_price - out["price"]
            out["par_participation"] = ppn.solve_participation(b.issue_price, b.notional, b.reference_level, b.spot, b.tenor_years,
                                                               b.risk_free_rate, b.dividend_yield, b.volatility)
        if b.mc_check:
            if not (1000 <= b.n_paths <= 2_000_000):
                raise ValueError("경로 수는 1,000~2,000,000 범위여야 함")
            mc = ppn.mc_price(*a, n_paths=b.n_paths, seed=b.seed)
            mc["diff"] = mc["price"] - out["price"]
            mc["within_2se"] = abs(mc["diff"]) <= 2 * mc["std_error"]
            out["mc"] = mc
    except ValueError as e:
        raise HTTPException(422, str(e))
    out.update({"model": "ZERO_COUPON_BOND_PLUS_BSM_CALL", "model_version": ppn.MODEL_VERSION, "result_label": "MODEL ESTIMATE",
                "perspective": "투자자 보유 1개. 발행자 포지션은 반대 부호"})
    out["valuation_id"] = log_valuation("simple_note", b.model_dump(), {k: out[k] for k in ("price", "bond_value", "option_value")},
                                        model_version=ppn.MODEL_VERSION)
    return out
