import pytest

from app.quant.autocallable_payoff import AutocallSpec
from app.quant.monte_carlo import McConfig, McMarket, build_schedule, bumped, simulate
from app.quant.numerical_greeks import els_price_and_greeks

SPEC = AutocallSpec()
SCH = build_schedule(SPEC)
MK = McMarket(500, 400, 500, 400, 0.18, 0.24, 0.012, 0.006, 0.04, 0.85)
CFG = McConfig(n_paths=20000, seed=42)


@pytest.fixture(scope="module")
def out():
    return els_price_and_greeks(SPEC, SCH, MK, CFG)


def test_investor_signs(out):
    g = out["greeks"]
    assert g["delta_1"] + g["delta_2"] > 0          # 기초자산 상승 시 투자자 가치 상승
    assert g["vega_1_per_1volpt"] + g["vega_2_per_1volpt"] < 0   # 변동성 상승 시 투자자 가치 하락
    assert g["theta_per_calendar_day"] is None      # 제공하지 않는 값을 숫자로 만들지 않음


def test_vega_and_rho_units_match_repricing(out):
    g = out["greeks"]
    base, vol_up, rate_up = simulate(SPEC, SCH, [MK, bumped(MK, sigma2=MK.sigma2 + 0.01), bumped(MK, r=MK.r + 0.01)], CFG, detail_index=None)
    assert g["vega_2_per_1volpt"] == pytest.approx(vol_up.price - base.price, rel=0.15)
    assert g["rho_per_100bp"] == pytest.approx(rate_up.price - base.price, rel=0.15)


def test_delta_consistent_with_large_shock(out):
    g = out["greeks"]
    base, up, dn = simulate(SPEC, SCH, [MK, bumped(MK, s2=404), bumped(MK, s2=396)], CFG, detail_index=None)
    assert g["delta_2"] == pytest.approx((up.price - dn.price) / 8.0, rel=0.25)


def test_bump_stability_table(out):
    assert [r["bump_pct"] for r in out["bump_stability"]] == [0.25, 0.5, 1.0]
    assert out["base"].price == pytest.approx(simulate(SPEC, SCH, [MK], CFG)[0].price, rel=1e-12)
