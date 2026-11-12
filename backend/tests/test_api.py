import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.quant.black_scholes import bsm

P = "/api/v1"
OPT = {"underlying": "SPY", "option_type": "CALL", "spot": 600.0, "strike": 600.0, "valuation_date": "2026-11-12", "expiry": "2027-02-12",
       "risk_free_rate": 0.04, "dividend_yield": 0.01, "volatility": 0.20, "multiplier": 100, "signed_quantity": -1}


@pytest.fixture(scope="module")
def c():
    client = TestClient(app)
    r = client.post(P + "/market/refresh", json={"mode": "synthetic"})   # 네트워크 없이 실행
    assert r.status_code == 200
    client.post(P + "/book/reset", json={})
    return client


def test_health(c):
    assert c.get(P + "/health").json()["trading"] == "disabled"


def test_synthetic_snapshot_is_labelled(c):
    s = c.get(P + "/market/snapshot/active").json()
    assert s["mode"] == "SYNTHETIC DEMO" and s["as_of"]
    assert all(v["label"] == "SYNTHETIC DEMO" for v in s["inputs"]["spots"].values())
    assert s["inputs"]["curve"][0]["approximation"] is True
    assert c.get(P + "/market/options/SPY").json()["available"] is False   # 가상 모드에서 시장 IV를 만들지 않음
    assert len(c.get(P + "/market/history/SPY").json()["rows"]) > 250


def test_european_matches_engine_and_reacts_to_spot(c):
    r = c.post(P + "/pricing/european", json={**OPT, "spot_shock_pct": 5, "curves": True}).json()
    ref = bsm("CALL", 600, 600, 92 / 365, 0.04, 0.01, 0.20)
    assert r["model_price_per_share_usd"] == pytest.approx(ref.price)
    assert r["signed_position_mtm_usd"] == pytest.approx(-ref.price * 100)
    assert r["greeks_position"]["delta_shares"] == pytest.approx(-ref.delta * 100)
    assert r["hedge_shares_for_delta_neutral"] == pytest.approx(ref.delta * 100)   # 콜 매도는 주식 매수로 헤지
    sc = r["shock_compare"]
    assert abs(sc["error_delta_gamma"]) < abs(sc["error_delta_only"])
    up = c.post(P + "/pricing/european", json={**OPT, "spot": 630.0}).json()
    assert up["model_price_per_share_usd"] > r["model_price_per_share_usd"]
    assert abs(up["greeks_position"]["delta_shares"]) > abs(r["greeks_position"]["delta_shares"])
    assert c.get(P + "/valuations/" + r["valuation_id"]).json()["inputs"]["spot"] == 600.0
    assert c.post(P + "/pricing/european", json={**OPT, "spot": -1}).status_code == 422


def test_implied_vol_endpoint(c):
    price = bsm("PUT", 600, 580, 92 / 365, 0.04, 0.01, 0.27).price
    body = {"market_price": price, "option_type": "PUT", "spot": 600, "strike": 580, "valuation_date": "2026-11-12", "expiry": "2027-02-12",
            "risk_free_rate": 0.04, "dividend_yield": 0.01}
    assert c.post(P + "/pricing/implied-vol", json=body).json()["implied_vol"] == pytest.approx(0.27, abs=1e-6)
    bad = c.post(P + "/pricing/implied-vol", json={**body, "market_price": 0.0001, "strike": 700}).json()
    assert bad["implied_vol"] is None and bad["status"] != "OK"


MKT = {"spot_1": 500, "spot_2": 400, "vol_1": 0.18, "vol_2": 0.24, "div_1": 0.012, "div_2": 0.006, "rate": 0.04, "corr": 0.85}


def test_structuring_price_and_terms_change(c):
    a = c.post(P + "/structuring/price", json={"market": MKT, "n_paths": 6000}).json()
    assert a["distribution"]["fraction_sum"] == pytest.approx(1.0)
    assert a["investor"]["ci95"][0] < a["investor"]["price_per_note"] < a["investor"]["ci95"][1]
    assert a["issuer_position"]["mtm"] == pytest.approx(-10 * a["investor"]["price_per_note"])
    assert a["issuer_position"]["hedge_shares"]["2"] == pytest.approx(10 * a["greeks_investor_per_note"]["delta_2"])
    assert a["greeks_investor_per_note"]["theta_per_calendar_day"] is None
    assert a["spot_shock"]["down_10pct"]["change"] < 0 < a["spot_shock"]["up_10pct"]["change"]
    b = c.post(P + "/structuring/price", json={"market": MKT, "n_paths": 6000, "spec": {"ki_barrier": 0.7, "coupon_rate": 0.06}}).json()
    assert b["investor"]["price_per_note"] < a["investor"]["price_per_note"]
    assert b["distribution"]["loss_rate"] > a["distribution"]["loss_rate"]
    assert c.post(P + "/structuring/price", json={"market": {**MKT, "corr": 1.5}}).status_code == 422


def test_payoff_examples_call_contract_function(c):
    ex = {e["id"]: e["result"] for e in c.post(P + "/structuring/payoff", json={}).json()["examples"]}
    assert ex["early"]["amount"] == 1050 and ex["maturity"]["amount"] == 1200
    assert ex["ki_recover"]["amount"] == 1150 and ex["ki_recover"]["knocked_in"] is True
    assert ex["ki_loss"]["amount"] == pytest.approx(700)
    custom = c.post(P + "/structuring/payoff", json={"points": [[0.5, 0.8], [1.0, 0.5], [2.0, 0.3]]}).json()["result"]
    assert custom["amount"] == pytest.approx(300)


def test_book_risk_hedge_and_stress_flow(c):
    risk = c.post(P + "/risk/portfolio", json={"n_paths": 6000}).json()
    assert [r["signed_quantity"] for r in risk["rows"]] == [-1, 1, -10, 0, 0]
    d0 = risk["totals"]["delta"]
    plan = c.post(P + "/hedge/delta", json={"n_paths": 6000}).json()
    assert plan["applied"] is False and plan["plan"]["SPY"]["trade_shares"] == round(-d0["SPY"])
    stress0 = c.post(P + "/risk/stress", json={"n_paths": 6000, "scenarios": [{"id": "dn", "name": "dn", "spot_pct": {"SPY": -1, "QQQ": -1}}]}).json()
    applied = c.post(P + "/hedge/delta", json={"n_paths": 6000, "apply": True}).json()
    assert applied["applied"] is True
    after = c.post(P + "/risk/portfolio", json={"n_paths": 6000}).json()
    for u in ("SPY", "QQQ"):
        assert abs(after["totals"]["delta"][u]) <= 0.5 + 1e-9   # 정수 주식 반올림 잔여
    assert after["totals"]["vega"] == pytest.approx(risk["totals"]["vega"])   # 델타 헤지 후에도 베가는 남음
    stress1 = c.post(P + "/risk/stress", json={"n_paths": 6000, "scenarios": [{"id": "dn", "name": "dn", "spot_pct": {"SPY": -1, "QQQ": -1}}]}).json()
    assert abs(stress1["scenarios"][0]["pnl_full_reprice"]) < abs(stress0["scenarios"][0]["pnl_full_reprice"])
    assert len(c.get(P + "/book").json()["hedge_trades"]) == 2


def test_manual_snapshot_changes_two_screens(c):
    base = c.get(P + "/market/snapshot/active").json()
    r0 = c.post(P + "/risk/portfolio", json={"snapshot_id": base["snapshot_id"], "n_paths": 6000}).json()
    m = c.post(P + "/market/manual", json={"base_snapshot_id": base["snapshot_id"], "vols": {"QQQ": 0.35}, "rate": 0.05}).json()["snapshot"]
    assert m["mode"] == "MANUAL SCENARIO" and m["inputs"]["vols"]["QQQ"]["label"] == "MANUAL SCENARIO"
    assert m["inputs"]["spots"]["SPY"]["label"] == "SYNTHETIC DEMO"   # 바꾸지 않은 값의 표기는 유지
    r1 = c.post(P + "/risk/portfolio", json={"snapshot_id": m["snapshot_id"], "n_paths": 6000}).json()
    assert r1["rows"][1]["mtm"] > r0["rows"][1]["mtm"] and r1["rows"][2]["mtm"] != r0["rows"][2]["mtm"]
    s = c.post(P + "/risk/stress", json={"snapshot_id": m["snapshot_id"], "n_paths": 6000}).json()
    assert len(s["scenarios"]) == 9 and s["data"]["mode"] == "MANUAL SCENARIO"
    assert c.post(P + "/market/manual", json={"corr": 2}).status_code == 422


def test_position_patch_versions_instrument(c):
    pos = c.get(P + "/book").json()["positions"][0]
    new = c.patch(P + f"/book/positions/{pos['id']}", json={"signed_quantity": -2, "spec_changes": {"strike": pos["spec"]["strike"] + 10}}).json()
    assert new["signed_quantity"] == -2 and new["version"] == pos["version"] + 1 and new["instrument_id"] != pos["instrument_id"]
    assert c.patch(P + "/book/positions/nope", json={"signed_quantity": 1}).status_code == 404


def test_backtest_and_heatmap(c):
    bt = c.post(P + "/hedge/backtest", json={}).json()
    assert [r["rebalance_every"] for r in bt["runs"]] == [1, 5, 0] and "시작일 이후 자료 미사용" in bt["sigma_source"]
    hm = c.post(P + "/risk/heatmap", json={"n_paths": 2000}).json()
    assert hm["change"][2][2] == 0 and hm["change"][0][0] < 0 < hm["change"][4][4] + 1e9
