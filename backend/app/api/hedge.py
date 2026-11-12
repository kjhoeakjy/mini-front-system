from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.market import UNDERLYINGS
from ..quant.hedging import delta_hedge, hedge_backtest, realized_vol
from ..services import book_service
from ..services.valuation_service import book_risk, labels, mc_config, snapshot_or_404

router = APIRouter(prefix="/hedge", tags=["hedge"])


class DeltaIn(BaseModel):
    snapshot_id: Optional[str] = None
    n_paths: int = 20000
    seed: int = 42
    integer_shares: bool = True
    cost_bps: float = 1.0
    fixed_fee: float = 0.0
    apply: bool = False   # True면 가상 장부의 현물 수량만 변경한다. 주문은 내지 않는다.


@router.post("/delta")
def delta(b: DeltaIn):
    snap, cfg = snapshot_or_404(b.snapshot_id), mc_config(b.n_paths, b.seed)
    rep, positions, inp = book_risk(snap, cfg)
    stock = {p["spec"]["underlying"]: p for p in positions if p["instrument_type"] == "SPOT"}
    cur = {u: (stock[u]["signed_quantity"] if u in stock else 0.0) for u in UNDERLYINGS}
    plan = delta_hedge(rep["totals"]["delta"], inp.spots, cur, rep["totals"]["gamma"], b.integer_shares, b.cost_bps, b.fixed_fee)
    applied = False
    if b.apply:
        for u in UNDERLYINGS:
            t = plan[u]["trade_shares"]
            if t == 0:
                continue
            if u in stock:
                book_service.update_position(stock[u]["id"], qty=cur[u] + t)
            else:
                book_service.add_position("SPOT", f"{u} 현물", {"underlying": u, "currency": "USD"}, t)
            book_service.record_hedge(u, t, inp.spots[u], plan[u]["estimated_cost"], snap["snapshot_id"])
        applied = True
    return {"plan": plan, "applied": applied, "data": labels(snap), "result_label": "MODEL ESTIMATE",
            "remaining": {"gamma": rep["totals"]["gamma"], "vega": rep["totals"]["vega"], "rho": rep["totals"]["rho"]},
            "messages": ["델타 헤지는 기초자산 가격의 작은 변동에 대한 일차 노출을 줄임",
                         "감마가 0이 아니므로 가격이 크게 움직이면 델타가 다시 변함",
                         "베가가 0이 아니므로 변동성이 변하면 손익이 발생함",
                         "반복 헤지는 거래 비용을 발생시키며 손실 방지를 보장하지 않음"],
            "order_notice": "가상 거래. 실제 주문·계좌 연동 없음"}


class BacktestIn(BaseModel):
    snapshot_id: Optional[str] = None
    ticker: str = "SPY"
    start: Optional[date] = None
    end: Optional[date] = None
    sigma: Optional[float] = None     # 생략 시 시작일 이전 60거래일 실현변동성
    rate: Optional[float] = None      # 생략 시 스냅샷의 최단기 금리
    cost_bps: float = 1.0
    frequencies: list = [1, 5, 0]     # 재헤지 간격(거래일). 0 = 헤지 없음


@router.post("/backtest")
def backtest(b: BacktestIn):
    snap = snapshot_or_404(b.snapshot_id)
    if b.ticker not in UNDERLYINGS:
        raise HTTPException(404, "지원 종목: SPY, QQQ")
    hist = snap["history"][b.ticker]
    ds = [date.fromisoformat(h["date"]) for h in hist]
    px = [h["adj_close"] for h in hist]
    end = b.end or ds[-1]
    i1 = max(i for i, d in enumerate(ds) if d <= end)
    i0 = min((i for i, d in enumerate(ds) if d >= b.start), default=None) if b.start else i1 - 126
    if i0 is None or i0 < 0 or i1 - i0 < 5:
        raise HTTPException(422, "기간이 자료 범위를 벗어나거나 너무 짧음")
    if b.sigma is not None:
        sigma, sig_src = b.sigma, "수동 입력"
    else:
        if i0 < 61:
            raise HTTPException(422, "시작일 이전 자료가 60거래일 미만임. 변동성을 직접 입력해야 함")
        sigma, sig_src = realized_vol(px[i0 - 60: i0 + 1]), "시작일 이전 60거래일 실현변동성(시작일 이후 자료 미사용)"
    rate = b.rate if b.rate is not None else snap["inputs"]["curve"][0]["value"]
    runs = []
    for f in b.frequencies[:4]:
        r = hedge_backtest(ds[i0: i1 + 1], px[i0: i1 + 1], sigma, rate, 0.0, int(f), b.cost_bps)
        runs.append({"rebalance_every": int(f), "name": "헤지 없음" if f == 0 else "매일" if f == 1 else f"{int(f)}거래일마다", **r})
    return {"ticker": b.ticker, "start": ds[i0].isoformat(), "end": ds[i1].isoformat(), "sigma": sigma, "sigma_source": sig_src, "rate": rate,
            "runs": runs, "data_label": snap["quotes"][b.ticker]["label"], "result_label": "MODEL ESTIMATE",
            "assumptions": ["콜 1계약(100주) 매도, 행사가는 시작일 가격, 만기는 종료일", "변동성과 금리는 기간 내 고정",
                            "조정종가 사용, 배당수익률 0 적용(배당은 조정종가에 반영된 것으로 봄)",
                            "현금계정: 프리미엄 유입, 매매 대금, 거래 비용, 이자 반영"]}
