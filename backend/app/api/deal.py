from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import book_service, snapshot_service
from ..services.valuation_service import snapshot_or_404
from .market import _slim

router = APIRouter(prefix="/deal", tags=["deal"])

# 기준 시나리오의 시장 입력. 실제 시세가 아닌 수기 입력값이다.
BASE_CASE = {"spots": {"SPY": 100.0}, "vols": {"SPY": 0.20}, "divs": {"SPY": 0.0}, "rate": 0.05}


class StartIn(BaseModel):
    source: str = "base"                 # base: 기준 시나리오(S=100), market: 지정 스냅샷의 시장 입력
    snapshot_id: Optional[str] = None


@router.post("/start")
def start(b: StartIn):
    """단일 거래 장부를 새 거래로 재생성한다. 다중 상품 장부와 저장된 스냅샷은 변경하지 않는다."""
    snap = snapshot_or_404(b.snapshot_id)
    if b.source == "base":
        snap = snapshot_service.manual(snap["snapshot_id"], BASE_CASE, prefix="base")
    elif b.source != "market":
        raise HTTPException(422, "source는 base 또는 market")
    return {"snapshot": _slim(snap), "positions": book_service.new_deal(snap), "book_name": book_service.DEAL, "source": b.source}
