from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..quant.black_scholes import MODEL_VERSION, bsm, position_greeks, year_fraction
from ..quant.implied_vol import implied_volatility
from ..storage.database import log_valuation

router = APIRouter(prefix="/pricing", tags=["pricing"])


class EuropeanIn(BaseModel):
    instrument_type: str = "EUROPEAN_OPTION"
    underlying: str = "SPY"
    option_type: str
    spot: float
    strike: float
    valuation_date: date
    expiry: date
    risk_free_rate: float
    dividend_yield: float
    volatility: float
    multiplier: float = 100
    signed_quantity: float = 1
    input_mode: str = "MANUAL SCENARIO"
    spot_shock_pct: Optional[float] = None   # 지정 시 손익 근사 비교를 함께 반환
    curves: bool = False                      # 지정 시 민감도 곡선을 함께 반환


def _price(b: EuropeanIn, **over):
    S = over.get("spot", b.spot)
    sig = over.get("volatility", b.volatility)
    T = over.get("T", year_fraction(b.valuation_date, b.expiry))
    return bsm(b.option_type, S, b.strike, T, b.risk_free_rate, b.dividend_yield, sig)


@router.post("/european")
def european(b: EuropeanIn):
    try:
        res = _price(b)
    except ValueError as e:
        raise HTTPException(422, str(e))
    T = year_fraction(b.valuation_date, b.expiry)
    scale = b.multiplier * b.signed_quantity
    out = {
        "model": "BLACK_SCHOLES_MERTON_EUROPEAN", "model_version": MODEL_VERSION, "input_mode": b.input_mode, "result_label": "MODEL ESTIMATE",
        "T_years": T, "d1": res.d1, "d2": res.d2,
        "model_price_per_share_usd": res.price, "model_price_per_contract_usd": res.price * b.multiplier,
        "signed_position_mtm_usd": res.price * scale,
        "greeks_per_share": {"delta": res.delta, "gamma": res.gamma, "vega_raw": res.vega_raw, "theta_annual": res.theta_annual, "rho_raw": res.rho_raw},
        "greeks_position": position_greeks(res, b.multiplier, b.signed_quantity),
        "units": {"delta_shares": "기초자산 $1 상승 시 가치 변화 (주식 환산 수량)", "gamma_per_usd": "기초자산 $1 상승 시 Delta 변화",
                  "vega_per_1volpt_usd": "변동성 +1%p 시 가치 변화", "theta_per_calendar_day_usd": "1일 경과 시 가치 변화",
                  "rho_per_100bp_usd": "금리 +100bp 시 가치 변화"},
        "hedge_shares_for_delta_neutral": None if res.delta is None else -res.delta * scale,
        "warnings": ["가상 장외 유럽형 현금결제 계약 기준. 상장 SPY·QQQ 옵션(미국형)의 거래소 가격이 아님"] + ([res.note] if res.note else []),
    }
    if b.spot_shock_pct is not None and res.delta is not None:
        dS = b.spot * b.spot_shock_pct / 100.0
        full = (_price(b, spot=b.spot + dS).price - res.price) * scale
        d_only = res.delta * dS * scale
        dg = d_only + 0.5 * res.gamma * dS * dS * scale
        out["shock_compare"] = {"spot_shock_pct": b.spot_shock_pct, "delta_only": d_only, "delta_gamma": dg, "full_reprice": full,
                                "error_delta_only": d_only - full, "error_delta_gamma": dg - full}
    if b.curves and T > 0:
        spots = [b.spot * (0.7 + 0.6 * i / 40) for i in range(41)]
        by_spot = []
        for s in spots:
            r = _price(b, spot=s)
            by_spot.append({"spot": s, "price": r.price * scale, "delta": (r.delta or 0) * scale, "gamma": (r.gamma or 0) * scale,
                            "payoff": (max(s - b.strike, 0) if b.option_type.upper() == "CALL" else max(b.strike - s, 0)) * scale})
        days = max((b.expiry - b.valuation_date).days, 1)
        by_time = []
        for d in sorted({max(1, int(round(days * i / 30))) for i in range(1, 31)}):
            r = _price(b, T=d / 365.0)
            by_time.append({"days_to_expiry": d, "theta_per_day": (r.theta_annual or 0) / 365.0 * scale, "price": r.price * scale})
        by_vol = [{"vol": v / 100.0, "price": _price(b, volatility=v / 100.0).price * scale} for v in range(5, 61, 2)]
        out["curves"] = {"by_spot": by_spot, "by_time": by_time, "by_vol": by_vol}
    out["valuation_id"] = log_valuation("european", b.model_dump(mode="json"), {k: v for k, v in out.items() if k != "curves"}, model_version=MODEL_VERSION)
    return out


class IvIn(BaseModel):
    market_price: float
    option_type: str
    spot: float
    strike: float
    valuation_date: date
    expiry: date
    risk_free_rate: float
    dividend_yield: float


@router.post("/implied-vol")
def implied_vol(b: IvIn):
    T = year_fraction(b.valuation_date, b.expiry)
    r = implied_volatility(b.market_price, b.option_type, b.spot, b.strike, T, b.risk_free_rate, b.dividend_yield)
    return {"implied_vol": r.implied_vol, "status": r.status, "message": r.message, "no_arbitrage_lower": r.lower_bound,
            "no_arbitrage_upper": r.upper_bound, "T_years": T,
            "note": "미국형 상장 옵션 호가를 넣은 경우 유럽형 모형 기준 대용치(European-model-implied proxy)임"}
