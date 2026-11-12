from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..domain.market import UNDERLYINGS
from ..quant.monte_carlo import MODEL_VERSION, bumped, build_schedule, simulate
from ..quant.portfolio_risk import NOTE, note_market, note_spec
from ..quant.stress import PRESETS, run_scenarios
from ..services.valuation_service import book_risk, labels, mc_config, snapshot_or_404
from ..storage.database import log_valuation

router = APIRouter(prefix="/risk", tags=["stress"])


class StressIn(BaseModel):
    snapshot_id: Optional[str] = None
    book: str = "DEMO"
    n_paths: int = 20000
    seed: int = 42
    scenarios: Optional[list] = None   # 생략 시 기본 시나리오 전체


@router.get("/stress/presets")
def presets():
    return {"presets": PRESETS}


@router.post("/stress")
def stress(b: StressIn):
    snap, cfg = snapshot_or_404(b.snapshot_id), mc_config(b.n_paths, b.seed)
    rep, positions, inp = book_risk(snap, cfg, b.book)
    out = run_scenarios(positions, inp, b.scenarios or PRESETS, cfg, rep["totals"])
    out.update({"positions": [{"id": p["id"], "name": p["name"], "instrument_type": p["instrument_type"]} for p in positions], "data": labels(snap), "result_label": "MODEL ESTIMATE",
                "definition": "시나리오 손익 = 충격 후 장부 평가금액 - 기준 장부 평가금액. VaR나 손실 확률 예측이 아님"})
    out["valuation_id"] = log_valuation("stress", b.model_dump(), {"scenarios": [{k: s[k] for k in ("id", "pnl_full_reprice")} for s in out["scenarios"]]},
                                        snap["snapshot_id"], MODEL_VERSION, cfg.seed, cfg.n_paths)
    return out


class HeatIn(BaseModel):
    snapshot_id: Optional[str] = None
    n_paths: int = 8000
    seed: int = 42
    shocks_pct: list = [-20, -10, 0, 10, 20]


@router.post("/heatmap")
def heatmap(b: HeatIn):
    """SPY·QQQ 현물 충격 조합별 노트 이론가 변화(투자자 보유 1개 기준)."""
    snap, cfg = snapshot_or_404(b.snapshot_id), mc_config(b.n_paths, b.seed)
    _, positions, inp = book_risk(snap, mc_config())
    notes = [p for p in positions if p["instrument_type"] == NOTE]
    if not notes:
        return {"available": False, "reason": "장부에 노트가 없음"}
    pos = notes[0]
    spec, mk = note_spec(pos["spec"]), note_market(pos["spec"], inp)
    sh = [float(x) for x in b.shocks_pct[:9]]
    grid = [bumped(mk, s1=mk.s1 * (1 + a / 100), s2=mk.s2 * (1 + c / 100)) for c in sh for a in sh]
    res = simulate(spec, build_schedule(spec, inp.as_of), [mk] + grid, cfg, detail_index=None)
    base = res[0].price
    cells = [[res[1 + i * len(sh) + j].price - base for j in range(len(sh))] for i in range(len(sh))]
    return {"available": True, "shocks_pct": sh, "x": UNDERLYINGS[0], "y": UNDERLYINGS[1], "base_price": base, "change": cells,
            "std_error": res[0].std_error, "n_paths": cfg.n_paths, "seed": cfg.seed, "position_quantity": pos["signed_quantity"],
            "note": "행은 QQQ 충격, 열은 SPY 충격. 기준가 고정, 같은 난수로 평가", "result_label": "MODEL ESTIMATE", "data": labels(snap)}
