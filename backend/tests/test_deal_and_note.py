"""단일 거래 흐름과 원금지급형 채권의 기준값 검증."""
import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.quant import principal_protected_note as ppn
from app.quant.black_scholes import bsm, position_greeks

A = dict(N=1000.0, alpha=0.5, S0=100.0, S=100.0, T=1.0, r=0.05, q=0.0, sigma=0.20)


@pytest.fixture(scope="module")
def c():
    return TestClient(app)


def test_base_case_reference_values():
    res = bsm("CALL", 100, 100, 1.0, 0.05, 0.0, 0.20)
    g = position_greeks(res, 100, -1)
    assert res.price == pytest.approx(10.4505835722, abs=1e-9)
    assert res.price * 100 * -1 == pytest.approx(-1045.05835722, abs=1e-7)
    assert g["delta_shares"] == pytest.approx(-63.68306512, abs=1e-7)
    assert g["gamma_per_usd"] == pytest.approx(-1.8762, abs=1e-4)
    assert g["vega_per_1volpt_usd"] == pytest.approx(-37.52, abs=5e-3)


def test_note_payoff_examples():
    assert [ppn.payoff(1000, 0.5, 100, s) for s in (80, 100, 120)] == pytest.approx([1000, 1000, 1100])


def test_note_price_is_bond_plus_call():
    out = ppn.price(**A)
    call = bsm("CALL", 100, 100, 1.0, 0.05, 0.0, 0.20)
    assert out["bond_value"] == pytest.approx(1000 * math.exp(-0.05))
    assert out["price"] == pytest.approx(1000 * math.exp(-0.05) + 0.5 * 1000 / 100 * call.price)
    assert out["price"] == pytest.approx(out["bond_value"] + out["option_value"])
    assert ppn.price(**{**A, "alpha": 0.0})["price"] == pytest.approx(out["bond_value"])
    assert ppn.price(**{**A, "alpha": 0.8})["price"] >= out["price"]


def test_note_greeks_match_call_scaled_and_bumps():
    out, call = ppn.price(**A), bsm("CALL", 100, 100, 1.0, 0.05, 0.0, 0.20)
    u, g = 0.5 * 1000 / 100, out["greeks"]
    assert g["delta_shares"] == pytest.approx(u * call.delta)
    assert g["gamma_per_usd"] == pytest.approx(u * call.gamma)
    assert g["vega_per_1volpt_usd"] == pytest.approx(u * call.vega_raw * 0.01)
    h = 1e-4
    assert g["delta_shares"] == pytest.approx((ppn.price(**{**A, "S": 100 + h})["price"] - ppn.price(**{**A, "S": 100 - h})["price"]) / (2 * h), rel=1e-6)
    assert g["rho_per_100bp_usd"] == pytest.approx((ppn.price(**{**A, "r": 0.05 + h})["price"] - ppn.price(**{**A, "r": 0.05 - h})["price"]) / (2 * h) * 0.01, rel=1e-6)
    assert g["theta_per_calendar_day_usd"] == pytest.approx(-(ppn.price(**{**A, "T": 1 + h})["price"] - ppn.price(**{**A, "T": 1 - h})["price"]) / (2 * h) / 365, rel=1e-6)


def test_note_par_participation_and_mc():
    a = ppn.solve_participation(1000, 1000, 100, 100, 1.0, 0.05, 0.0, 0.20)
    assert ppn.price(**{**A, "alpha": a})["price"] == pytest.approx(1000)
    assert ppn.solve_participation(900, 1000, 100, 100, 1.0, 0.05, 0.0, 0.20) is None
    mc = ppn.mc_price(**A, n_paths=200000, seed=7)
    assert abs(mc["price"] - ppn.price(**A)["price"]) < 3 * mc["std_error"]
    assert ppn.mc_price(**A, n_paths=20000, seed=7) == ppn.mc_price(**A, n_paths=20000, seed=7)


def test_deal_flow_price_hedge_stress(c):
    adv = c.get("/api/v1/book").json()["positions"]
    adv_trades = c.get("/api/v1/book").json()["hedge_trades"]
    d = c.post("/api/v1/deal/start", json={"source": "base"}).json()
    sid, opt = d["snapshot"]["snapshot_id"], d["positions"][0]
    assert c.get("/api/v1/market/snapshot/active").json()["snapshot_id"] != sid      # 기준 시나리오는 기본 스냅샷으로 선택되지 않음
    assert d["snapshot"]["mode"] == "MANUAL SCENARIO" and d["snapshot"]["inputs"]["spots"]["SPY"]["label"] == "MANUAL SCENARIO"
    assert opt["spec"]["strike"] == 100 and opt["signed_quantity"] == -1 and d["positions"][1]["signed_quantity"] == 0
    assert opt["spec"]["trade_price_per_share"] == pytest.approx(10.4505835722, abs=1e-9)
    body = {"snapshot_id": sid, "book": "DEAL"}
    r = c.post("/api/v1/risk/portfolio", json=body).json()
    assert r["totals"]["mtm"] == pytest.approx(-1045.05835722, abs=1e-6)
    assert r["totals"]["delta"]["SPY"] == pytest.approx(-63.68306512, abs=1e-6) and r["totals"]["delta"]["QQQ"] == 0
    sc = [{"id": "up5", "name": "+5%", "spot_pct": {"SPY": 5}}, {"id": "dn5", "name": "-5%", "spot_pct": {"SPY": -5}}, {"id": "v5", "name": "vol", "vol_pts": 5}]
    before = c.post("/api/v1/risk/stress", json={**body, "scenarios": sc}).json()["scenarios"]
    up_full = (bsm("CALL", 105, 100, 1.0, 0.05, 0.0, 0.20).price - 10.4505835722) * -100
    assert before[0]["pnl_full_reprice"] == pytest.approx(up_full, abs=1e-6)          # 행사가 100 유지
    assert before[0]["pnl_full_reprice"] != pytest.approx(before[0]["approx"]["delta_only"], abs=1.0)
    assert before[2]["pnl_full_reprice"] < 0                                           # 콜 매도: 변동성 상승 시 손실
    plan = c.post("/api/v1/hedge/delta", json={**body, "apply": True}).json()
    assert plan["plan"]["SPY"]["trade_shares"] == 64 and plan["plan"]["QQQ"]["trade_shares"] == 0
    book = c.get(f"/api/v1/book?book=DEAL&snapshot_id={sid}").json()
    assert book["positions"][1]["signed_quantity"] == 64 and len(book["hedge_trades"]) == 1
    again = c.post("/api/v1/hedge/delta", json=body).json()["plan"]["SPY"]
    assert again["trade_shares"] == 0 and again["net_delta_before"] == pytest.approx(0.31693488, abs=1e-6)
    after = c.post("/api/v1/risk/stress", json={**body, "scenarios": sc}).json()["scenarios"]
    assert after[0]["by_position"][0] == pytest.approx(before[0]["pnl_full_reprice"], abs=1e-6)
    assert after[0]["by_position"][1] == pytest.approx(64 * 5.0)
    assert abs(after[0]["pnl_full_reprice"]) < abs(before[0]["pnl_full_reprice"]) and after[0]["pnl_full_reprice"] != 0
    # 다중 상품 장부는 영향 없음
    assert c.get("/api/v1/book").json()["positions"] == adv
    assert c.get("/api/v1/book").json()["hedge_trades"] == adv_trades
    # 새 거래 생성 시 단일 거래 장부만 초기화
    c.post("/api/v1/deal/start", json={"source": "base"})
    assert c.get("/api/v1/book?book=DEAL").json()["positions"][1]["signed_quantity"] == 0
    assert c.get("/api/v1/book").json()["positions"] == adv


def test_deal_keeps_strike_when_market_changes(c):
    d = c.post("/api/v1/deal/start", json={"source": "base"}).json()
    m = c.post("/api/v1/market/manual", json={"base_snapshot_id": d["snapshot"]["snapshot_id"], "spots": {"SPY": 110}}).json()["snapshot"]
    pos = c.get(f"/api/v1/book?book=DEAL&snapshot_id={m['snapshot_id']}").json()["positions"][0]
    assert pos["spec"]["strike"] == 100 and pos["spec"]["trade_price_per_share"] == pytest.approx(10.4505835722, abs=1e-9)
    assert c.get("/api/v1/book?book=NONE").status_code == 422


def test_simple_structuring_api(c):
    b = {"reference_level": 100, "spot": 100, "risk_free_rate": 0.05, "dividend_yield": 0.0, "volatility": 0.2, "mc_check": True}
    r = c.post("/api/v1/simple-structuring/price", json=b).json()
    assert r["price"] == pytest.approx(ppn.price(**A)["price"]) and r["mc"]["within_2se"] in (True, False)
    assert [e["payoff"] for e in r["examples"]] == pytest.approx([1000, 1000, 1100])
    assert r["issue_minus_model"] == pytest.approx(1000 - r["price"])
    assert c.post("/api/v1/simple-structuring/price", json={**b, "participation": 50}).status_code == 422
