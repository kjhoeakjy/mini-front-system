from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..quant.monte_carlo import MODEL_VERSION
from ..services import book_service
from ..services.valuation_service import book_risk, labels, mc_config, snapshot_or_404
from ..storage.database import get_valuation, log_valuation

router = APIRouter(tags=["portfolio"])


@router.get("/book")
def book(snapshot_id: Optional[str] = None):
    snap = snapshot_or_404(snapshot_id)
    return {"book_name": book_service.BOOK, "positions": book_service.ensure(snap), "hedge_trades": book_service.hedge_trades()}


class ResetIn(BaseModel):
    snapshot_id: Optional[str] = None


@router.post("/book/reset")
def reset(b: ResetIn):
    snap = snapshot_or_404(b.snapshot_id)
    return {"positions": book_service.reset(snap), "based_on_snapshot": snap["snapshot_id"]}


class PositionIn(BaseModel):
    instrument_type: str
    name: str
    spec: dict
    signed_quantity: float


@router.post("/book/positions")
def add_position(b: PositionIn):
    try:
        pid = book_service.add_position(b.instrument_type, b.name, b.spec, b.signed_quantity)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f"포지션 조건 오류: {e}")
    return {"position_id": pid}


class PatchIn(BaseModel):
    signed_quantity: Optional[float] = None
    spec_changes: Optional[dict] = None


@router.patch("/book/positions/{position_id}")
def patch_position(position_id: str, b: PatchIn):
    try:
        return book_service.update_position(position_id, b.signed_quantity, b.spec_changes)
    except KeyError:
        raise HTTPException(404, "포지션 없음")
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"조건 오류: {e}")


class RiskIn(BaseModel):
    snapshot_id: Optional[str] = None
    n_paths: int = 20000
    seed: int = 42


@router.post("/risk/portfolio")
def risk_portfolio(b: RiskIn):
    snap, cfg = snapshot_or_404(b.snapshot_id), mc_config(b.n_paths, b.seed)
    rep, _, inp = book_risk(snap, cfg)
    out = {**rep, "data": labels(snap), "spots": inp.spots, "result_label": "MODEL ESTIMATE", "n_paths": cfg.n_paths, "seed": cfg.seed,
           "notes": ["평가금액(MTM)은 현재 모형 가치이며 손익이 아님. 손익 계산에는 거래가격 또는 이전 스냅샷이 필요함",
                     "노트 Theta를 제공하지 않으므로 장부 Theta 합계는 부분 집계임",
                     "1% 변동 손익은 자산별 단독 충격 기준이며 교차 감마를 포함하지 않음"]}
    out["valuation_id"] = log_valuation("portfolio", b.model_dump(), {"totals": rep["totals"]}, snap["snapshot_id"], MODEL_VERSION, cfg.seed, cfg.n_paths)
    return out


@router.get("/valuations/{valuation_id}")
def valuation(valuation_id: str):
    v = get_valuation(valuation_id)
    if not v:
        raise HTTPException(404, "평가 기록 없음")
    return v
