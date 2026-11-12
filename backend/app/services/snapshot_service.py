"""시장 스냅샷 생성·저장. 원자료를 검증해 평가 입력으로 정리한다."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ..domain.market import UNDERLYINGS
from ..providers import market_yahoo, rates_fred
from ..providers.base import ProviderError
from ..providers.offline_fixture import load_bundled_real, load_fixture
from ..storage.database import conn, new_id, now_utc

REAL, CACHED, MANUAL, SYNTH, MODEL = "REAL MARKET DATA", "CACHED REAL SNAPSHOT", "MANUAL SCENARIO", "SYNTHETIC DEMO", "MODEL ESTIMATE"
NY = ZoneInfo("America/New_York")
VOL_WINDOWS = (20, 60, 252)
MIN_CORR_OBS = 60
DEFAULT_MANUAL_RATE = 0.04


def _log_returns(vals: list) -> list:
    return [math.log(b / a) for a, b in zip(vals, vals[1:])]


def _std(x: list) -> float:
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def _corr(a: list, b: list) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def market_status(now: datetime | None = None) -> dict:
    n = (now or datetime.now(timezone.utc)).astimezone(NY)
    open_ = n.weekday() < 5 and (9, 30) <= (n.hour, n.minute) < (16, 0)
    return {"ny_time": n.isoformat(timespec="minutes"), "regular_session_open": open_,
            "note": "정규장 시간 기준 판정. 휴장일은 반영하지 않음"}


def build_snapshot(mode: str, tickers: dict, rates: list, rate_label: str, warnings: list | None = None) -> dict:
    """원자료에서 스냅샷을 만든다. 두 자산의 공통 최신 거래일을 기준일로 삼는다."""
    warnings, flags = list(warnings or []), []
    data_label = SYNTH if mode == SYNTH else REAL
    common = sorted(set.intersection(*[{h["date"] for h in tickers[u]["history"]} for u in UNDERLYINGS]))
    if len(common) < 30:
        raise ProviderError("두 자산의 공통 거래일이 30일 미만임")
    as_of = common[-1]
    for u in UNDERLYINGS:
        if tickers[u]["last_bar_date"] != as_of:
            flags.append(f"{u} 최신 거래일({tickers[u]['last_bar_date']})이 공통 기준일과 다름")
    by = {u: {h["date"]: h for h in tickers[u]["history"]} for u in UNDERLYINGS}
    rets = {u: _log_returns([by[u][d]["adj_close"] for d in common]) for u in UNDERLYINGS}
    spots, vols, divs, quotes, vol_table = {}, {}, {}, {}, {}
    for u in UNDERLYINGS:
        t = tickers[u]
        spot = by[u][as_of]["close"]
        quotes[u] = {"price": spot, "price_type": "종가(미조정)", "observed_at": f"{as_of}T16:00:00-NY", "trade_date": as_of,
                     "source": t["source"], "fetched_at": t.get("fetched_at"), "currency": "USD", "adjustment": "unadjusted",
                     "quality_flags": t.get("quality_flags", []), "label": data_label}
        spots[u] = {"value": spot, "label": data_label, "source": t["source"], "unit": "USD/주"}
        rv = {}
        for w in VOL_WINDOWS:
            rv[str(w)] = _std(rets[u][-w:]) * math.sqrt(252) if len(rets[u]) >= w else None
            if rv[str(w)] is None:
                flags.append(f"{u} 실현변동성 {w}일: 자료 부족")
        vol_table[u] = rv
        chosen = rv["252"] or rv["60"] or rv["20"]
        vols[u] = {"value": chosen, "label": SYNTH if mode == SYNTH else MODEL, "unit": "연율 소수",
                   "source": "실현변동성(조정종가 로그수익률 표준편차 × √252). 내재변동성의 대용치"}
        if t.get("dividend_yield") is not None:
            q, qsrc = t["dividend_yield"], "가상 입력"
        elif t.get("dividends_ttm") is not None:
            q, qsrc = t["dividends_ttm"] / spot, "최근 12개월 배당 합계 / 현물가 (연속 배당수익률 근사)"
        else:
            q, qsrc = 0.0, "배당 자료 없음: 0으로 가정"
            warnings.append(f"{u} 배당 자료를 구하지 못해 0으로 가정함")
        divs[u] = {"value": q, "label": SYNTH if mode == SYNTH else MODEL, "source": qsrc, "unit": "연율 소수"}
    n_corr = min(252, len(common) - 1)
    corr_val = _corr(rets["SPY"][-n_corr:], rets["QQQ"][-n_corr:])
    if n_corr < MIN_CORR_OBS:
        flags.append(f"상관계수 관측 수 {n_corr}개: 최소 {MIN_CORR_OBS}개 미만")
    corr = {"value": corr_val, "label": SYNTH if mode == SYNTH else MODEL, "n_obs": n_corr,
            "source": f"최근 {n_corr}거래일 로그수익률의 Pearson 상관계수. 위험중립 상관계수의 대용치"}
    curve = [{"series": r["series"], "tenor_years": r["tenor_years"], "value": r["value"], "label": rate_label,
              "observed_date": r["observed_date"], "source": r["source"], "approximation": True} for r in rates]
    fetched = now_utc()
    stale_days = (date.today() - date.fromisoformat(as_of)).days
    if mode != SYNTH and stale_days > 4:
        flags.append(f"기준일이 {stale_days}일 전임 (stale)")
    return {
        "snapshot_id": new_id("snap"), "mode": mode, "as_of": as_of, "created_at": fetched, "parent_id": None,
        "quotes": quotes, "rates": rates, "realized_vol": vol_table,
        "inputs": {"spots": spots, "vols": vols, "divs": divs, "curve": curve, "corr": corr},
        "history": {u: [{"date": d, "close": by[u][d]["close"], "adj_close": by[u][d]["adj_close"]} for d in common] for u in UNDERLYINGS},
        "quality_flags": flags, "warnings": warnings,
        "rate_method": "국채 고정만기 수익률을 평탄한 연속복리 금리로 근사. 만기 사이는 선형 보간",
    }


def save(snap: dict) -> dict:
    body = json.dumps(snap, ensure_ascii=False)
    snap["hash"] = hashlib.sha256(body.encode()).hexdigest()[:16]
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO market_snapshots VALUES (?,?,?,?,?,?)",
                  (snap["snapshot_id"], snap["created_at"], snap["as_of"], snap["mode"], snap.get("parent_id"),
                   json.dumps(snap, ensure_ascii=False)))
    return snap


def get(snapshot_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT body FROM market_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    return json.loads(r["body"]) if r else None


def latest(mode: str | None = None) -> dict | None:
    with conn() as c:
        if mode:
            r = c.execute("SELECT body FROM market_snapshots WHERE mode=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (mode,)).fetchone()
        else:
            r = c.execute("SELECT body FROM market_snapshots ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
    return json.loads(r["body"]) if r else None


def list_all() -> list:
    with conn() as c:
        rows = c.execute("SELECT id, created_at, as_of, mode, parent_id FROM market_snapshots ORDER BY created_at DESC, rowid DESC").fetchall()
    return [dict(r) for r in rows]


def synthetic() -> dict:
    fx = load_fixture()
    return save(build_snapshot(SYNTH, fx["tickers"], fx["rates"], SYNTH, ["가상 자료로 구성한 스냅샷. 실제 시장 수치가 아님"]))


def refresh(mode: str = "auto") -> dict:
    """mode: auto(실제, 캐시, 가상 순), real(실패 시 오류), synthetic."""
    if mode == "synthetic":
        return {"snapshot": synthetic(), "status": [{"step": "가상 자료", "ok": True, "message": "가상 스냅샷 생성"}]}
    status = []
    try:
        tickers = {u: market_yahoo.fetch_ticker(u) for u in UNDERLYINGS}
        status.append({"step": "시세(yfinance)", "ok": True, "message": "수집 성공"})
    except ProviderError as e:
        status.append({"step": "시세(yfinance)", "ok": False, "message": str(e)})
        if mode == "real":
            raise ProviderError(str(e))
        cached = latest(REAL)
        if cached:
            snap = copy.deepcopy(cached)
            snap.update({"snapshot_id": new_id("snap"), "mode": CACHED, "parent_id": cached["snapshot_id"], "created_at": now_utc()})
            snap["warnings"] = snap.get("warnings", []) + [f"실시간 수집 실패로 {cached['created_at']} 수집분을 재사용함"]
            for sec in ("spots", "vols", "divs"):
                for u in UNDERLYINGS:
                    if snap["inputs"][sec][u]["label"] == REAL:
                        snap["inputs"][sec][u]["label"] = CACHED
            status.append({"step": "캐시", "ok": True, "message": "저장된 실제 스냅샷 사용"})
            return {"snapshot": save(snap), "status": status}
        raw = load_bundled_real()
        if raw:
            snap = build_snapshot(REAL, raw["tickers"], raw["rates"], CACHED if raw.get("rates_real") else MANUAL,
                                  [f"실시간 수집 불가. {raw.get('fetched_at', '')} 수집분 사용"])
            snap["mode"] = CACHED
            for sec in ("spots", "vols", "divs"):
                for u in UNDERLYINGS:
                    if snap["inputs"][sec][u]["label"] == REAL:
                        snap["inputs"][sec][u]["label"] = CACHED
            for u in UNDERLYINGS:
                snap["quotes"][u]["label"] = CACHED
            status.append({"step": "캐시", "ok": True, "message": "배포 시점 수집분 사용"})
            return {"snapshot": save(snap), "status": status}
        status.append({"step": "캐시", "ok": False, "message": "저장된 실제 스냅샷 없음. 가상 자료로 전환"})
        return {"snapshot": synthetic(), "status": status}
    warnings = []
    try:
        rates, rate_label = rates_fred.fetch_all(), REAL
        status.append({"step": "금리(FRED)", "ok": True, "message": "수집 성공"})
    except ProviderError as e:
        status.append({"step": "금리(FRED)", "ok": False, "message": str(e)})
        rates = [{"series": s, "tenor_years": t, "value_pct": DEFAULT_MANUAL_RATE * 100, "value": DEFAULT_MANUAL_RATE,
                  "observed_date": None, "fetched_at": None, "source": "수동 가정값", "unit": "연율 소수", "approximation": True}
                 for s, t in rates_fred.SERIES.items()]
        rate_label = MANUAL
        warnings.append(f"금리 수집 실패로 수동 가정값 {DEFAULT_MANUAL_RATE:.2%}를 사용함. 시장 화면에서 수정 가능")
    return {"snapshot": save(build_snapshot(REAL, tickers, rates, rate_label, warnings)), "status": status}


def manual(base_id: str, overrides: dict) -> dict:
    """기존 스냅샷의 평가 입력 일부를 수동 값으로 바꾼 새 스냅샷. 원본은 유지한다."""
    base = get(base_id)
    if not base:
        raise KeyError(base_id)
    snap = copy.deepcopy(base)
    snap.update({"snapshot_id": new_id("snap"), "mode": MANUAL, "parent_id": base_id, "created_at": now_utc()})
    inp = snap["inputs"]
    for sec in ("spots", "vols", "divs"):
        for u, v in (overrides.get(sec) or {}).items():
            if u in UNDERLYINGS and v is not None:
                if sec != "divs" and float(v) <= 0:
                    raise ValueError(f"{u} {sec} 값은 0보다 커야 함")
                inp[sec][u].update({"value": float(v), "label": MANUAL, "source": "수동 입력"})
    if overrides.get("rate") is not None:
        for p in inp["curve"]:
            p.update({"value": float(overrides["rate"]), "label": MANUAL, "source": "수동 입력(전 만기 동일)"})
    if overrides.get("corr") is not None:
        cv = float(overrides["corr"])
        if not (-0.999 <= cv <= 0.999):
            raise ValueError("상관계수는 -0.999~0.999 범위여야 함")
        inp["corr"].update({"value": cv, "label": MANUAL, "source": "수동 입력"})
    snap["warnings"] = [w for w in snap.get("warnings", [])] + ["일부 입력을 수동 값으로 변경한 시나리오"]
    return save(snap)


def active() -> dict:
    """가장 최근 스냅샷. 없으면 가상 스냅샷을 만든다."""
    return latest() or synthetic()
