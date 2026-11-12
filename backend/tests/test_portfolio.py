from datetime import date

import pytest

from app.domain.market import MarketInputs
from app.quant.black_scholes import bsm
from app.quant.monte_carlo import McConfig
from app.quant.portfolio_risk import reprice, risk_report
from app.quant.stress import run_scenarios

INP = MarketInputs(date(2025, 6, 30), {"SPY": 500.0, "QQQ": 400.0}, {"SPY": 0.16, "QQQ": 0.21}, {"SPY": 0.012, "QQQ": 0.006},
                   ((0.25, 0.042), (1.0, 0.04), (2.0, 0.039)), 0.84)
CFG = McConfig(n_paths=6000, seed=42)
CALL = {"id": "a", "name": "SPY call", "instrument_type": "EUROPEAN_OPTION", "signed_quantity": -1,
        "spec": {"underlying": "SPY", "option_type": "CALL", "strike": 500.0, "expiry": "2025-09-28", "multiplier": 100}}
PUT = {"id": "b", "name": "QQQ put", "instrument_type": "EUROPEAN_OPTION", "signed_quantity": 1,
       "spec": {"underlying": "QQQ", "option_type": "PUT", "strike": 400.0, "expiry": "2025-12-27", "multiplier": 100}}
NOTE = {"id": "c", "name": "note", "instrument_type": "AUTOCALLABLE_NOTE", "signed_quantity": -10,
        "spec": {"underlyings": ["SPY", "QQQ"], "notional": 1000.0, "tenor_years": 2.0, "autocall_times": [0.5, 1.0, 1.5],
                 "autocall_barriers": [0.95, 0.9, 0.85], "maturity_barrier": 0.8, "ki_barrier": 0.6, "coupon_rate": 0.1,
                 "reference_levels": {"SPY": 500.0, "QQQ": 400.0}}}
STOCK = {"id": "d", "name": "SPY", "instrument_type": "SPOT", "signed_quantity": 7, "spec": {"underlying": "SPY"}}
BOOK = [CALL, PUT, NOTE, STOCK]


@pytest.fixture(scope="module")
def rep():
    return risk_report(BOOK, INP, CFG)


def test_option_row_sign_and_multiplier(rep):
    T = 90 / 365
    res = bsm("CALL", 500, 500, T, INP.rate(T), 0.012, 0.16)
    row = rep["rows"][0]
    assert row["mtm"] == pytest.approx(-res.price * 100)
    assert row["delta"]["SPY"] == pytest.approx(-res.delta * 100) and row["delta"]["QQQ"] == 0
    assert rep["rows"][1]["delta"]["QQQ"] < 0 and rep["rows"][1]["mtm"] > 0


def test_spot_and_note_rows(rep):
    assert rep["rows"][3]["delta"] == {"SPY": 7.0, "QQQ": 0.0} and rep["rows"][3]["mtm"] == pytest.approx(3500.0)
    note = rep["rows"][2]
    assert note["mtm"] < 0 and note["theta"] is None      # 발행자 매도 포지션
    assert note["delta"]["SPY"] + note["delta"]["QQQ"] < 0  # 투자자와 부호 반대


def test_totals_are_per_underlying_sums(rep):
    for u in ("SPY", "QQQ"):
        assert rep["totals"]["delta"][u] == pytest.approx(sum(r["delta"][u] for r in rep["rows"]))
        assert rep["totals"]["dollar_delta"][u] == pytest.approx(rep["totals"]["delta"][u] * INP.spots[u])
    assert rep["totals"]["mtm"] == pytest.approx(sum(r["mtm"] for r in rep["rows"]))
    assert rep["totals"]["theta_complete"] is False


def test_scenario_pnl_is_shocked_minus_base(rep):
    sc = [{"id": "x", "name": "x", "spot_pct": {"SPY": -10, "QQQ": -10}}, {"id": "v", "name": "v", "vol_pts": 5}]
    out = run_scenarios(BOOK, INP, sc, CFG, rep["totals"])
    shocked, _ = INP.shocked({"SPY": -10, "QQQ": -10})
    direct = reprice(BOOK, [INP, shocked], CFG)
    assert out["scenarios"][0]["pnl_full_reprice"] == pytest.approx(direct[1]["total"] - direct[0]["total"])
    assert out["scenarios"][0]["by_position"][3] == pytest.approx(7 * -50.0)
    assert sum(out["scenarios"][0]["by_position"]) == pytest.approx(out["scenarios"][0]["pnl_full_reprice"])
    assert out["scenarios"][1]["approx"]["delta_only"] == 0


def test_shock_does_not_touch_contract_terms():
    shocked, _ = INP.shocked({"SPY": -10})
    assert shocked.spots["SPY"] == pytest.approx(450.0) and INP.spots["SPY"] == 500.0
    assert NOTE["spec"]["reference_levels"]["SPY"] == 500.0 and CALL["spec"]["strike"] == 500.0
    low, warns = INP.shocked(vol_pts=-30)
    assert low.vols["SPY"] == 0.01 and warns


def test_rate_interpolation():
    assert INP.rate(0.1) == 0.042 and INP.rate(5) == 0.039
    assert INP.rate(1.5) == pytest.approx(0.0395)
