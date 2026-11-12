"""지급 규칙 설명용 예시 경로. 꺾은선으로 만든 가상 경로이며 지급액은 payoff_path()가 계산한다."""
from __future__ import annotations

import numpy as np

from .autocallable_payoff import AutocallSpec, payoff_path
from .monte_carlo import build_schedule


def path_from_points(spec: AutocallSpec, points: list, gap: float = 0.03):
    """points: [(연, worst 비율), ...]. 자산 1이 worst, 자산 2는 gap만큼 높게 둔다."""
    sch = build_schedule(spec)
    n = sch.maturity_idx
    t = np.arange(n + 1) / 252.0
    pts = sorted([(0.0, 1.0)] + [(float(a), float(b)) for a, b in points if a > 0])
    if pts[-1][0] < spec.tenor_years:
        pts.append((spec.tenor_years, pts[-1][1]))
    w = np.interp(t, [p[0] for p in pts], [p[1] for p in pts])
    return t, w, w + gap, sch


def examples(spec: AutocallSpec) -> list:
    t1 = spec.autocall_times[0]
    b = spec.autocall_barriers
    below = [(tt, bb - 0.05) for tt, bb in zip(spec.autocall_times, b)]
    ki = spec.ki_barrier - 0.05
    return [
        {"id": "early", "name": "조기상환", "points": [(t1, b[0] + 0.02)]},
        {"id": "maturity", "name": "만기 정상상환", "points": below + [(spec.tenor_years, spec.maturity_barrier + 0.03)]},
        {"id": "ki_recover", "name": "낙인 후 회복", "points": [below[0], (t1 + 0.25, ki)] + [(tt, min(bb - 0.05, 0.75)) for tt, bb in zip(spec.autocall_times[1:-1], b[1:-1])] + [(spec.autocall_times[-1], b[-1] + 0.01)]},
        {"id": "ki_loss", "name": "낙인 후 손실", "points": [below[0], (t1 + 0.25, ki), (spec.autocall_times[1], 0.65), (spec.autocall_times[-1], 0.68), (spec.tenor_years, 0.70)]},
    ]


def evaluate(spec: AutocallSpec, points: list) -> dict:
    t, r1, r2, sch = path_from_points(spec, points)
    res = payoff_path(spec, r1, r2, sch.obs_idx, sch.maturity_idx)
    sel = list(range(0, len(t), 5))
    if sel[-1] != len(t) - 1:
        sel.append(len(t) - 1)
    return {"amount": res.amount, "redeem_time": res.redeem_time, "category": res.category, "knocked_in": res.knocked_in,
            "worst_at_redeem": res.worst_at_redeem, "steps": res.steps, "pnl_vs_notional": res.amount - spec.notional,
            "path": [{"t": round(float(t[i]), 4), "ratio1": round(float(r1[i]), 4), "ratio2": round(float(r2[i]), 4)} for i in sel]}
