"""가상 장부. 계약 조건(instrument)은 불변이며 조건을 바꾸면 새 버전으로 저장한다."""
from __future__ import annotations

import json
from datetime import date, timedelta

from ..quant.autocallable_payoff import AutocallSpec
from ..quant.portfolio_risk import NOTE, OPTION, SPOT, note_spec
from ..storage.database import conn, new_id, now_utc

BOOK = "DEMO"


def default_note_spec(spots: dict, as_of: str) -> dict:
    s = AutocallSpec()
    return {"product_id": s.product_id, "underlyings": list(s.underlyings), "notional": s.notional, "tenor_years": s.tenor_years,
            "autocall_times": list(s.autocall_times), "autocall_barriers": list(s.autocall_barriers),
            "maturity_barrier": s.maturity_barrier, "ki_barrier": s.ki_barrier, "coupon_rate": s.coupon_rate,
            "reference_levels": {"SPY": spots["SPY"], "QQQ": spots["QQQ"]}, "issue_date": as_of, "currency": "USD"}


def _validate(itype: str, spec: dict):
    if itype == OPTION:
        if spec["option_type"] not in ("CALL", "PUT") or spec["strike"] <= 0:
            raise ValueError("옵션 조건 오류")
        date.fromisoformat(spec["expiry"])
    elif itype == NOTE:
        note_spec(spec)
        if min(spec["reference_levels"].values()) <= 0:
            raise ValueError("기준가는 0보다 커야 함")
    elif itype != SPOT:
        raise ValueError("지원하지 않는 상품 유형")


def add_position(itype: str, name: str, spec: dict, qty: float, order: int | None = None) -> str:
    _validate(itype, spec)
    iid, pid = new_id("ins"), new_id("pos")
    with conn() as c:
        if order is None:
            order = (c.execute("SELECT COALESCE(MAX(sort_order),0) m FROM positions").fetchone()["m"] or 0) + 1
        c.execute("INSERT INTO instruments VALUES (?,?,?,?,?,?)", (iid, itype, name, 1, json.dumps(spec, ensure_ascii=False), now_utc()))
        c.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)", (pid, iid, BOOK, qty, order, None))
    return pid


def reset(snapshot: dict) -> list:
    """스냅샷의 현물가를 행사가·기준가로 하는 기본 장부를 다시 만든다."""
    spots = {u: v["value"] for u, v in snapshot["inputs"]["spots"].items()}
    as_of = date.fromisoformat(snapshot["as_of"])
    with conn() as c:
        c.execute("DELETE FROM positions"); c.execute("DELETE FROM instruments"); c.execute("DELETE FROM virtual_hedge_trades")
    add_position(OPTION, "SPY 유럽형 콜 (90일)", {"underlying": "SPY", "option_type": "CALL", "strike": spots["SPY"],
                 "expiry": (as_of + timedelta(days=90)).isoformat(), "multiplier": 100, "currency": "USD"}, -1, 1)
    add_position(OPTION, "QQQ 유럽형 풋 (180일)", {"underlying": "QQQ", "option_type": "PUT", "strike": spots["QQQ"],
                 "expiry": (as_of + timedelta(days=180)).isoformat(), "multiplier": 100, "currency": "USD"}, 1, 2)
    add_position(NOTE, "SPY·QQQ 스텝다운 노트", default_note_spec(spots, snapshot["as_of"]), -10, 3)
    add_position(SPOT, "SPY 현물", {"underlying": "SPY", "currency": "USD"}, 0, 4)
    add_position(SPOT, "QQQ 현물", {"underlying": "QQQ", "currency": "USD"}, 0, 5)
    return positions()


def positions() -> list:
    with conn() as c:
        rows = c.execute("""SELECT p.id, p.signed_quantity, p.book_name, i.id instrument_id, i.instrument_type, i.name, i.version, i.spec
                            FROM positions p JOIN instruments i ON i.id=p.instrument_id ORDER BY p.sort_order""").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["spec"] = json.loads(d["spec"])
        out.append(d)
    return out


def ensure(snapshot: dict) -> list:
    return positions() or reset(snapshot)


def update_position(pid: str, qty: float | None = None, spec_changes: dict | None = None) -> dict:
    with conn() as c:
        r = c.execute("SELECT p.*, i.instrument_type, i.name, i.version, i.spec FROM positions p JOIN instruments i ON i.id=p.instrument_id WHERE p.id=?", (pid,)).fetchone()
        if not r:
            raise KeyError(pid)
        if qty is not None:
            c.execute("UPDATE positions SET signed_quantity=? WHERE id=?", (qty, pid))
        if spec_changes:
            spec = {**json.loads(r["spec"]), **spec_changes}
            _validate(r["instrument_type"], spec)
            iid = new_id("ins")
            c.execute("INSERT INTO instruments VALUES (?,?,?,?,?,?)", (iid, r["instrument_type"], r["name"], r["version"] + 1,
                      json.dumps(spec, ensure_ascii=False), now_utc()))
            c.execute("UPDATE positions SET instrument_id=? WHERE id=?", (iid, pid))
    return next(p for p in positions() if p["id"] == pid)


def record_hedge(underlying: str, shares: float, price: float, cost: float, snapshot_id: str):
    with conn() as c:
        c.execute("INSERT INTO virtual_hedge_trades VALUES (?,?,?,?,?,?,?)", (new_id("trd"), now_utc(), underlying, shares, price, cost, snapshot_id))


def hedge_trades() -> list:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM virtual_hedge_trades ORDER BY created_at DESC, rowid DESC").fetchall()]
