"""지급 규칙 검증. 난수를 쓰지 않고 지정한 경로를 지급 함수에 직접 넣는다."""
import numpy as np
import pytest

from app.quant.autocallable_payoff import AutocallSpec, payoff_path, payoff_vectorized
from app.quant.example_paths import path_from_points
from app.quant.monte_carlo import build_schedule

SPEC = AutocallSpec()

CASES = {
    "A": ([(0.5, 0.97)], 1050.0, "AUTOCALL_1", False),
    "B": ([(0.5, 0.93), (1.0, 0.92)], 1100.0, "AUTOCALL_2", False),
    "C": ([(0.5, 0.90), (1.0, 0.85), (1.5, 0.80), (2.0, 0.83)], 1200.0, "MATURITY_ABOVE_BARRIER", False),
    "D": ([(0.5, 0.90), (1.0, 0.85), (1.5, 0.80), (2.0, 0.75)], 1200.0, "MATURITY_NO_KNOCK_IN", False),
    "E": ([(0.5, 0.90), (0.75, 0.55), (1.0, 0.65), (1.5, 0.68), (2.0, 0.70)], 700.0, "MATURITY_LOSS", True),
    "F": ([(0.5, 0.90), (0.75, 0.58), (1.0, 0.70), (1.5, 0.86)], 1150.0, "AUTOCALL_3", True),
    "G": ([(0.5, 0.80), (1.0, 0.60), (1.5, 0.45), (2.0, 0.30)], 300.0, "MATURITY_LOSS", True),
}


@pytest.mark.parametrize("name", list(CASES))
def test_term_sheet_cases(name):
    points, amount, category, ki = CASES[name]
    _, r1, r2, sch = path_from_points(SPEC, points)
    res = payoff_path(SPEC, r1, r2, sch.obs_idx, sch.maturity_idx)
    assert res.amount == pytest.approx(amount, abs=1e-9)
    assert res.category == category and res.knocked_in is ki


def test_barrier_equality_is_inclusive():
    _, r1, r2, sch = path_from_points(SPEC, [(0.5, 0.95)])
    assert payoff_path(SPEC, r1, r2, sch.obs_idx, sch.maturity_idx).amount == 1050.0
    _, r1, r2, sch = path_from_points(SPEC, [(0.5, 0.9), (1.0, 0.6), (1.5, 0.7), (2.0, 0.79)])
    assert payoff_path(SPEC, r1, r2, sch.obs_idx, sch.maturity_idx).category == "MATURITY_LOSS"   # W=0.60 도달은 낙인


def test_worst_of_uses_lower_asset():
    sch = build_schedule(SPEC)
    n = sch.maturity_idx + 1
    r1, r2 = np.full(n, 1.10), np.full(n, 0.90)   # 한 자산만 부진
    res = payoff_path(SPEC, r1, r2, sch.obs_idx, sch.maturity_idx)
    assert res.category == "AUTOCALL_2" and res.amount == 1100.0


def test_knock_in_after_autocall_is_ignored():
    sch = build_schedule(SPEC)
    n = sch.maturity_idx + 1
    r = np.full(n, 0.97)
    r[sch.obs_idx[0] + 10:] = 0.40   # 조기상환 이후의 급락
    res = payoff_path(SPEC, r, r, sch.obs_idx, sch.maturity_idx)
    assert res.amount == 1050.0 and res.knocked_in is False


def test_vectorized_matches_scalar_on_random_paths():
    rng = np.random.default_rng(7)
    sch = build_schedule(SPEC)
    steps = sch.maturity_idx
    x = np.cumsum(rng.standard_normal((2, 400, steps)) * 0.3 / np.sqrt(252), axis=2)
    r1 = np.concatenate([np.ones((400, 1)), np.exp(x[0])], axis=1)
    r2 = np.concatenate([np.ones((400, 1)), np.exp(x[1])], axis=1)
    w = np.minimum(r1, r2)
    amt, slot, cat = payoff_vectorized(SPEC, w[:, list(sch.obs_idx)], w[:, sch.maturity_idx], w.min(axis=1))
    seen = set()
    for i in range(400):
        res = payoff_path(SPEC, r1[i], r2[i], sch.obs_idx, sch.maturity_idx)
        assert res.amount == pytest.approx(amt[i]) and res.redeem_slot == slot[i] and res.category == SPEC.categories[cat[i]]
        seen.add(res.category)
    assert len(seen) >= 5   # 여러 범주가 실제로 검증되었는지 확인


def test_invalid_spec():
    with pytest.raises(ValueError):
        AutocallSpec(autocall_times=(0.5, 1.0), autocall_barriers=(0.9,))
    with pytest.raises(ValueError):
        AutocallSpec(autocall_times=(0.5, 2.5, 1.5))
