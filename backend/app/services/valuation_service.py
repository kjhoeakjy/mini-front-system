"""API에서 공통으로 쓰는 평가 흐름: 스냅샷 선택, 장부 평가, 결과 캐시."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException

from ..domain.market import MarketInputs, inputs_from_snapshot
from ..quant.monte_carlo import McConfig
from ..quant.portfolio_risk import risk_report
from . import book_service, snapshot_service

MAX_PATHS = 400000
_cache: dict = {}


def snapshot_or_404(snapshot_id: Optional[str]) -> dict:
    snap = snapshot_service.get(snapshot_id) if snapshot_id else snapshot_service.active()
    if not snap:
        raise HTTPException(404, "스냅샷을 찾을 수 없음")
    return snap


def mc_config(n_paths: int = 20000, seed: int = 42) -> McConfig:
    if not (1000 <= n_paths <= MAX_PATHS):
        raise HTTPException(422, f"경로 수는 1,000~{MAX_PATHS:,} 범위여야 함")
    return McConfig(n_paths=n_paths, seed=seed)


def book_risk(snap: dict, cfg: McConfig, book: str = book_service.BOOK) -> tuple[dict, list, MarketInputs]:
    try:
        positions = book_service.ensure(snap, book)
    except ValueError as e:
        raise HTTPException(422, str(e))
    inp = inputs_from_snapshot(snap)
    key = (snap["snapshot_id"], json.dumps(positions, sort_keys=True), cfg.n_paths, cfg.seed)
    if key not in _cache:
        if len(_cache) > 30:
            _cache.clear()
        _cache[key] = risk_report(positions, inp, cfg)
    return _cache[key], positions, inp


def labels(snap: dict) -> dict:
    i = snap["inputs"]
    return {"mode": snap["mode"], "as_of": snap["as_of"], "snapshot_id": snap["snapshot_id"],
            "spots": {u: v["label"] for u, v in i["spots"].items()}, "vols": {u: v["label"] for u, v in i["vols"].items()},
            "rate": i["curve"][0]["label"] if i["curve"] else None, "corr": i["corr"]["label"]}
