from datetime import date

import numpy as np
import pytest

from app.quant.autocallable_payoff import AutocallSpec
from app.quant.black_scholes import bsm
from app.quant.monte_carlo import McConfig, McMarket, build_schedule, bumped, mc_european_call, modified_following, simulate

SPEC = AutocallSpec()
SCH = build_schedule(SPEC)
MK = McMarket(500, 400, 500, 400, 0.18, 0.24, 0.012, 0.006, 0.04, 0.85)


def run(mk=MK, **kw):
    return simulate(SPEC, SCH, [mk], McConfig(**{"n_paths": 8000, "seed": 11, **kw}))[0]


def test_deterministic_for_same_seed():
    a, b = run(), run()
    assert a.price == b.price and a.category_fraction == b.category_fraction
    assert run(seed=12).price != a.price


def test_categories_are_exhaustive():
    r = run()
    assert sum(r.category_fraction.values()) == pytest.approx(1.0, abs=1e-12)
    assert r.n_paths == 8000 and r.ci_low < r.price < r.ci_high
    assert r.loss_rate <= r.knock_in_rate + r.category_fraction["MATURITY_LOSS"]
    assert r.min_payoff >= 0 and r.price <= SPEC.notional * (1 + SPEC.coupon_rate * SPEC.tenor_years)


def test_chunk_size_does_not_change_result():
    assert run(chunk_pairs=500).price == pytest.approx(run(chunk_pairs=4000).price, rel=1e-12)


def test_european_call_engine_check():
    price, se = mc_european_call(100, 100, 1.0, 0.05, 0.0, 0.2, 200000, 1)
    assert abs(price - bsm("CALL", 100, 100, 1.0, 0.05, 0.0, 0.2).price) < 3 * se


def test_correlated_normals_sample_correlation():
    rng = np.random.default_rng(3)
    z = rng.standard_normal((2, 200000))
    rho = 0.7
    z2 = rho * z[0] + np.sqrt(1 - rho ** 2) * z[1]
    assert np.corrcoef(z[0], z2)[0, 1] == pytest.approx(rho, abs=0.01)


def test_simulated_paths_have_target_correlation():
    r = simulate(SPEC, SCH, [MK], McConfig(n_paths=4000, seed=5, n_sample_paths=2000))[0]
    a, b = np.log(np.array(r.sample_paths["ratio1"])), np.log(np.array(r.sample_paths["ratio2"]))
    c = np.corrcoef(np.diff(a, axis=1).ravel(), np.diff(b, axis=1).ravel())[0, 1]
    assert c == pytest.approx(MK.rho, abs=0.02)


def test_spot_shock_keeps_reference_levels():
    """현물가만 내리면 기준가 대비 비율이 내려가 가치가 떨어져야 한다. 기준가를 함께 내리면 가치는 그대로다."""
    base, down, both = simulate(SPEC, SCH, [MK, bumped(MK, s1=450, s2=360), bumped(MK, s1=450, s2=360, s1_ref=450, s2_ref=360)],
                                McConfig(n_paths=8000, seed=11))
    assert down.price < base.price - 20
    assert both.price == pytest.approx(base.price, rel=1e-12)


def test_knock_in_at_valuation_is_observed():
    deep = bumped(MK, s1=250)   # 평가 시점 비율 0.5: 이미 낙인 수준
    r = run(deep)
    assert r.knock_in_rate == pytest.approx(1.0)


def test_standard_error_scales_with_paths():
    small, large = run(n_paths=2000), run(n_paths=32000)
    assert large.std_error < small.std_error
    assert small.std_error / large.std_error == pytest.approx(4.0, rel=0.35)   # 대략 1/√n


def test_monotonic_in_coupon_and_ki_barrier():
    cfg = McConfig(n_paths=8000, seed=11)
    hi_c = simulate(AutocallSpec(coupon_rate=0.12), SCH, [MK], cfg)[0].price
    lo_ki = simulate(AutocallSpec(ki_barrier=0.50), SCH, [MK], cfg)[0]
    assert hi_c > run().price and lo_ki.price > run().price and lo_ki.loss_rate < run().loss_rate


def test_schedule_dates_and_business_day_rule():
    assert modified_following(date(2025, 5, 31)) == date(2025, 5, 30)   # 토요일, 다음 평일이 6월이므로 앞당김
    assert modified_following(date(2025, 6, 1)) == date(2025, 6, 2)
    sch = build_schedule(SPEC, date(2025, 6, 30))
    assert [d.isoformat() for d in sch.dates] == ["2025-12-30", "2026-06-30", "2026-12-30", "2027-06-30"]
    assert sch.pay_times[-1] == pytest.approx(2.0, abs=0.01) and sch.maturity_idx == pytest.approx(504, abs=2)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        simulate(SPEC, SCH, [bumped(MK, sigma1=0.0)], McConfig(n_paths=1000))
    with pytest.raises(ValueError):
        simulate(SPEC, SCH, [bumped(MK, rho=1.2)], McConfig(n_paths=1000))
