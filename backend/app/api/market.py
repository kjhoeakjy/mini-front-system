from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.market import UNDERLYINGS
from ..providers import market_yahoo
from ..providers.base import ProviderError
from ..quant.black_scholes import bsm
from ..quant.implied_vol import implied_volatility
from ..services import snapshot_service
from ..services.valuation_service import snapshot_or_404

router = APIRouter(prefix="/market", tags=["market"])


class RefreshIn(BaseModel):
    mode: str = "auto"   # auto | real | synthetic


class ManualIn(BaseModel):
    base_snapshot_id: Optional[str] = None
    spots: dict = {}
    vols: dict = {}
    divs: dict = {}
    rate: Optional[float] = None
    corr: Optional[float] = None


def _slim(snap: dict) -> dict:
    out = {k: v for k, v in snap.items() if k != "history"}
    out["history_rows"] = {u: len(snap["history"][u]) for u in UNDERLYINGS}
    out["market_status"] = snapshot_service.market_status()
    return out


@router.post("/refresh")
def refresh(body: RefreshIn):
    if body.mode not in ("auto", "real", "synthetic"):
        raise HTTPException(422, "mode는 auto, real, synthetic 중 하나")
    try:
        r = snapshot_service.refresh(body.mode)
    except ProviderError as e:
        raise HTTPException(502, f"실제 자료 수집 실패: {e}")
    return {"snapshot": _slim(r["snapshot"]), "status": r["status"]}


@router.post("/manual")
def manual(body: ManualIn):
    base = snapshot_or_404(body.base_snapshot_id)
    try:
        snap = snapshot_service.manual(base["snapshot_id"], body.model_dump(exclude={"base_snapshot_id"}))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"snapshot": _slim(snap)}


@router.get("/snapshots")
def snapshots():
    return {"snapshots": snapshot_service.list_all()}


@router.get("/snapshot/{snapshot_id}")
def snapshot(snapshot_id: str):
    return _slim(snapshot_or_404(None if snapshot_id == "active" else snapshot_id))


@router.get("/snapshot/{snapshot_id}/export")
def export(snapshot_id: str):
    """재현용 전체 내보내기(원자료 포함)."""
    return snapshot_or_404(None if snapshot_id == "active" else snapshot_id)


@router.get("/history/{ticker}")
def history(ticker: str, snapshot_id: Optional[str] = None):
    snap = snapshot_or_404(snapshot_id)
    if ticker not in UNDERLYINGS:
        raise HTTPException(404, "지원 종목: SPY, QQQ")
    return {"ticker": ticker, "snapshot_id": snap["snapshot_id"], "label": snap["quotes"][ticker]["label"],
            "source": snap["quotes"][ticker]["source"], "rows": snap["history"][ticker]}


@router.get("/options/{ticker}")
def options(ticker: str, expiry: Optional[str] = None, snapshot_id: Optional[str] = None):
    """상장 옵션 체인과 유럽형 BSM 비교. 상장 ETF 옵션은 미국형이므로 참고용이다."""
    snap = snapshot_or_404(snapshot_id)
    if ticker not in UNDERLYINGS:
        raise HTTPException(404, "지원 종목: SPY, QQQ")
    if snap["mode"] == snapshot_service.SYNTH:
        return {"available": False, "reason": "가상 스냅샷에서는 옵션 체인을 제공하지 않음. 시장 관측 IV 없음"}
    try:
        expiries = market_yahoo.fetch_expiries(ticker)
        if not expiries:
            return {"available": False, "reason": "만기 목록이 비어 있음"}
        if expiry is None:
            today = date.today()
            expiry = min(expiries, key=lambda e: abs((date.fromisoformat(e) - today).days - 90))
        chain = market_yahoo.fetch_option_chain(ticker, expiry)
    except ProviderError as e:
        return {"available": False, "reason": str(e)}
    i = snap["inputs"]
    S, q, sig = i["spots"][ticker]["value"], i["divs"][ticker]["value"], i["vols"][ticker]["value"]
    T = (date.fromisoformat(expiry) - date.fromisoformat(snap["as_of"])).days / 365.0
    r = min(i["curve"], key=lambda p: abs(p["tenor_years"] - T))["value"]
    rows = []
    for row in chain["rows"]:
        k = row["strike"]
        if k is None or abs(k / S - 1) > 0.10 or T <= 0:
            continue
        row["model_price_snapshot_vol"] = bsm(row["option_type"], S, k, T, r, q, sig).price
        if row["mid"]:
            iv = implied_volatility(row["mid"], row["option_type"], S, k, T, r, q)
            row["european_model_implied_proxy"], row["iv_status"] = iv.implied_vol, iv.status
        else:
            row["european_model_implied_proxy"], row["iv_status"] = None, "IV unavailable"
        rows.append(row)
    return {"available": True, "ticker": ticker, "expiry": expiry, "expiries": expiries, "T": T, "spot_used": S, "r_used": r,
            "rows": rows, "source": chain["source"], "snapshot_time": chain["snapshot_time"], "label": "REAL MARKET DATA",
            "warnings": ["상장 ETF 옵션은 미국형이며 모형은 유럽형임. 역산값은 유럽형 모형 기준 대용치",
                         "호가 수집 시각과 스냅샷 기준일이 다를 수 있음", "변동성 곡면을 구성한 것이 아님"]}
