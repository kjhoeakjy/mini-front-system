"""장부 평가와 위험 집계.

부호 규칙: signed_quantity는 매수 +, 매도 -. Delta는 기초자산별 주식 환산 수량.
서로 다른 기초자산의 Delta는 합산하지 않고 자산별로 제시한다.
"""
from __future__ import annotations

from dataclasses import fields
from datetime import date
from typing import Sequence

from ..domain.market import UNDERLYINGS, MarketInputs
from .autocallable_payoff import AutocallSpec
from .black_scholes import bsm, position_greeks, year_fraction
from .monte_carlo import McConfig, McMarket, build_schedule, simulate
from .numerical_greeks import els_price_and_greeks

OPTION, NOTE, SPOT = "EUROPEAN_OPTION", "AUTOCALLABLE_NOTE", "SPOT"


def note_spec(spec: dict) -> AutocallSpec:
    names = {f.name for f in fields(AutocallSpec)}
    kw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in spec.items() if k in names}
    return AutocallSpec(**kw)


def note_market(spec: dict, inp: MarketInputs) -> McMarket:
    u1, u2 = spec.get("underlyings", UNDERLYINGS)
    ref = spec["reference_levels"]
    return McMarket(s1=inp.spots[u1], s2=inp.spots[u2], s1_ref=ref[u1], s2_ref=ref[u2],
                    sigma1=inp.vols[u1], sigma2=inp.vols[u2], q1=inp.divs[u1], q2=inp.divs[u2],
                    r=inp.rate(float(spec.get("tenor_years", 2.0))), rho=inp.corr)


def _zero() -> dict:
    return {u: 0.0 for u in UNDERLYINGS}


def _option_row(pos: dict, inp: MarketInputs) -> dict:
    s = pos["spec"]
    u, qty, mult = s["underlying"], pos["signed_quantity"], s.get("multiplier", 100)
    T = year_fraction(inp.as_of, date.fromisoformat(s["expiry"]))
    r = inp.rate(max(T, 0.0))
    res = bsm(s["option_type"], inp.spots[u], s["strike"], T, r, inp.divs[u], inp.vols[u])
    g = position_greeks(res, mult, qty)
    delta, gamma, vega = _zero(), _zero(), _zero()
    delta[u], gamma[u], vega[u] = g["delta_shares"] or 0.0, g["gamma_per_usd"] or 0.0, g["vega_per_1volpt_usd"] or 0.0
    warn = ["가상 장외 유럽형 계약. 상장 미국형 옵션 가격과 다름"]
    if res.note:
        warn.append(res.note)
    return {"unit_price": res.price * mult, "mtm": res.price * mult * qty, "delta": delta, "gamma": gamma, "vega": vega,
            "theta": g["theta_per_calendar_day_usd"], "rho": g["rho_per_100bp_usd"] or 0.0, "model": "BSM",
            "warnings": warn, "detail": {"T": T, "r": r, "q": inp.divs[u], "sigma": inp.vols[u], "per_share": res.price,
                                         "delta_per_share": res.delta}}


def _note_row(pos: dict, inp: MarketInputs, cfg: McConfig) -> dict:
    s, qty = pos["spec"], pos["signed_quantity"]
    spec, mk = note_spec(s), note_market(s, inp)
    out = els_price_and_greeks(spec, build_schedule(spec, inp.as_of), mk, cfg)
    g, base = out["greeks"], out["base"]
    u1, u2 = spec.underlyings
    delta, gamma, vega = _zero(), _zero(), _zero()
    delta[u1], delta[u2] = g["delta_1"] * qty, g["delta_2"] * qty
    gamma[u1], gamma[u2] = g["gamma_1"] * qty, g["gamma_2"] * qty
    vega[u1], vega[u2] = g["vega_1_per_1volpt"] * qty, g["vega_2_per_1volpt"] * qty
    warn = ["발행 시점 평가 단순화", "실현변동성·과거 상관계수 사용 시 대용치"] + out["warnings"]
    return {"unit_price": base.price, "mtm": base.price * qty, "delta": delta, "gamma": gamma, "vega": vega,
            "theta": None, "rho": g["rho_per_100bp"] * qty, "model": "MC-GBM", "warnings": warn,
            "detail": {"std_error": base.std_error, "n_paths": base.n_paths, "seed": cfg.seed, "r": mk.r,
                       "mtm_std_error": base.std_error * abs(qty)}}


def _spot_row(pos: dict, inp: MarketInputs) -> dict:
    u, qty = pos["spec"]["underlying"], pos["signed_quantity"]
    delta = _zero()
    delta[u] = float(qty)
    return {"unit_price": inp.spots[u], "mtm": inp.spots[u] * qty, "delta": delta, "gamma": _zero(), "vega": _zero(),
            "theta": 0.0, "rho": 0.0, "model": "Spot", "warnings": ["가상 보유. 실제 주문 없음"], "detail": {}}


def risk_report(positions: Sequence[dict], inp: MarketInputs, cfg: McConfig) -> dict:
    rows = []
    for pos in positions:
        t = pos["instrument_type"]
        row = _option_row(pos, inp) if t == OPTION else _note_row(pos, inp, cfg) if t == NOTE else _spot_row(pos, inp)
        row.update({"position_id": pos["id"], "name": pos["name"], "instrument_type": t,
                    "signed_quantity": pos["signed_quantity"], "label": "MODEL ESTIMATE"})
        rows.append(row)
    tot = {"mtm": sum(r["mtm"] for r in rows), "delta": _zero(), "gamma": _zero(), "vega": _zero(),
           "rho": sum(r["rho"] for r in rows)}
    for r in rows:
        for u in UNDERLYINGS:
            tot["delta"][u] += r["delta"][u]; tot["gamma"][u] += r["gamma"][u]; tot["vega"][u] += r["vega"][u]
    tot["dollar_delta"] = {u: tot["delta"][u] * inp.spots[u] for u in UNDERLYINGS}
    tot["theta_partial"] = sum(r["theta"] for r in rows if r["theta"] is not None)
    tot["theta_complete"] = all(r["theta"] is not None for r in rows)
    tot["one_pct_move"] = {u: {
        "delta_only": tot["delta"][u] * 0.01 * inp.spots[u],
        "delta_gamma": tot["delta"][u] * 0.01 * inp.spots[u] + 0.5 * tot["gamma"][u] * (0.01 * inp.spots[u]) ** 2,
    } for u in UNDERLYINGS}
    return {"rows": rows, "totals": tot,
            "unmeasured_risks": ["환율", "발행자·거래상대방 신용", "유동성·호가 스프레드", "모형 위험(변동성 곡면, 점프)", "교차 감마", "조기 행사"]}


def reprice(positions: Sequence[dict], inputs_list: Sequence[MarketInputs], cfg: McConfig) -> list:
    """각 시장 입력에서 포지션별 평가금액. 노트는 모든 입력을 같은 난수로 평가한다."""
    n = len(inputs_list)
    out = [[0.0] * len(positions) for _ in range(n)]
    se = [0.0] * len(positions)
    for j, pos in enumerate(positions):
        t, qty = pos["instrument_type"], pos["signed_quantity"]
        if t == OPTION:
            s = pos["spec"]
            for i, inp in enumerate(inputs_list):
                T = year_fraction(inp.as_of, date.fromisoformat(s["expiry"]))
                res = bsm(s["option_type"], inp.spots[s["underlying"]], s["strike"], T, inp.rate(max(T, 0.0)),
                          inp.divs[s["underlying"]], inp.vols[s["underlying"]])
                out[i][j] = res.price * s.get("multiplier", 100) * qty
        elif t == NOTE:
            spec = note_spec(pos["spec"])
            res = simulate(spec, build_schedule(spec, inputs_list[0].as_of),
                           [note_market(pos["spec"], inp) for inp in inputs_list], cfg, detail_index=None)
            for i in range(n):
                out[i][j] = res[i].price * qty
            se[j] = res[0].std_error * abs(qty)
        else:
            for i, inp in enumerate(inputs_list):
                out[i][j] = inp.spots[pos["spec"]["underlying"]] * qty
    return [{"values": v, "total": sum(v), "mc_std_error": se} for v in out]
