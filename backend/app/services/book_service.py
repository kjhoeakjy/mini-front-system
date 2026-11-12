"""가상 장부. 계약 조건(instrument)은 불변이며 조건을 바꾸면 새 버전으로 저장한다."""
from __future__ import annotations

import json
from datetime import date, timedelta

from ..domain.market import inputs_from_snapshot
from ..quant.autocallable_payoff import AutocallSpec
from ..quant.black_scholes import bsm
from ..quant.portfolio_risk import NOTE, OPTION, SPOT, note_spec
from ..storage.database import conn, new_id, now_utc

BOOK = "DEMO"     # 다중 상품 장부
DEAL = "DEAL"     # 단일 거래 장부 (SPY 콜 1계약 매도 + SPY 현물)
BOOKS = (BOOK, DEAL)


def check_book(book: str) -> str:
    if book not in BOOKS:
        raise ValueError(f"장부는 {BOOKS} 중 하나여야 함")
    return book


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


def add_position(itype: str, name: str, spec: dict, qty: float, order: int | None = None, book: str = BOOK) -> str:
    _validate(itype, spec)
    iid, pid = new_id("ins"), new_id("pos")
    with conn() as c:
        if order is None:
            order = (c.execute("SELECT COALESCE(MAX(sort_order),0) m FROM positions WHERE book_name=?", (book,)).fetchone()["m"] or 0) + 1
        c.execute("INSERT INTO instruments VALUES (?,?,?,?,?,?)", (iid, itype, name, 1, json.dumps(spec, ensure_ascii=False), now_utc()))
        c.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)", (pid, iid, book, qty, order, None))
    return pid


def _clear(book: str):
    with conn() as c:
        c.execute("DELETE FROM instruments WHERE id IN (SELECT instrument_id FROM positions WHERE book_name=?)", (book,))
        c.execute("DELETE FROM positions WHERE book_name=?", (book,))
        c.execute("DELETE FROM virtual_hedge_trades WHERE book_name=?", (book,))


def reset(snapshot: dict, book: str = BOOK) -> list:
    """스냅샷의 현물가를 행사가·기준가로 하는 기본 장부를 재생성한다. 지정한 장부 외에는 변경하지 않는다."""
    if check_book(book) == DEAL:
        return new_deal(snapshot)
    spots = {u: v["value"] for u, v in snapshot["inputs"]["spots"].items()}
    as_of = date.fromisoformat(snapshot["as_of"])
    _clear(book)
    add_position(OPTION, "SPY 유럽형 콜 (90일)", {"underlying": "SPY", "option_type": "CALL", "strike": spots["SPY"],
                 "expiry": (as_of + timedelta(days=90)).isoformat(), "multiplier": 100, "currency": "USD"}, -1, 1, book)
    add_position(OPTION, "QQQ 유럽형 풋 (180일)", {"underlying": "QQQ", "option_type": "PUT", "strike": spots["QQQ"],
                 "expiry": (as_of + timedelta(days=180)).isoformat(), "multiplier": 100, "currency": "USD"}, 1, 2, book)
    add_position(NOTE, "SPY·QQQ 스텝다운 노트", default_note_spec(spots, snapshot["as_of"]), -10, 3, book)
    add_position(SPOT, "SPY 현물", {"underlying": "SPY", "currency": "USD"}, 0, 4, book)
    add_position(SPOT, "QQQ 현물", {"underlying": "QQQ", "currency": "USD"}, 0, 5, book)
    return positions(book)


def new_deal(snapshot: dict, days: int = 365) -> list:
    """단일 거래 장부: SPY 유럽형 콜 1계약 매도(등가격, 만기 365일)와 SPY 현물 0주.

    행사가와 체결 프리미엄은 거래 시점 스냅샷으로 확정되며 이후 시장 입력이 바뀌어도 유지된다.
    """
    inp = inputs_from_snapshot(snapshot)
    as_of, S = inp.as_of, inp.spots["SPY"]
    T = days / 365.0
    prem = bsm("CALL", S, S, T, inp.rate(T), inp.divs["SPY"], inp.vols["SPY"]).price
    _clear(DEAL)
    add_position(OPTION, "SPY 유럽형 콜", {"underlying": "SPY", "option_type": "CALL", "strike": S,
                 "expiry": (as_of + timedelta(days=days)).isoformat(), "multiplier": 100, "currency": "USD",
                 "trade_date": snapshot["as_of"], "trade_spot": S, "trade_price_per_share": prem,
                 "trade_snapshot_id": snapshot["snapshot_id"]}, -1, 1, DEAL)
    add_position(SPOT, "SPY 현물", {"underlying": "SPY", "currency": "USD"}, 0, 2, DEAL)
    return positions(DEAL)


def positions(book: str = BOOK) -> list:
    with conn() as c:
        rows = c.execute("""SELECT p.id, p.signed_quantity, p.book_name, i.id instrument_id, i.instrument_type, i.name, i.version, i.spec
                            FROM positions p JOIN instruments i ON i.id=p.instrument_id WHERE p.book_name=? ORDER BY p.sort_order""", (check_book(book),)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["spec"] = json.loads(d["spec"])
        out.append(d)
    return out


def ensure(snapshot: dict, book: str = BOOK) -> list:
    return positions(book) or reset(snapshot, book)


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
    return next(p for p in positions(r["book_name"]) if p["id"] == pid)


def record_hedge(underlying: str, shares: float, price: float, cost: float, snapshot_id: str, book: str = BOOK):
    with conn() as c:
        c.execute("INSERT INTO virtual_hedge_trades VALUES (?,?,?,?,?,?,?,?)", (new_id("trd"), now_utc(), underlying, shares, price, cost, snapshot_id, book))


def hedge_trades(book: str = BOOK) -> list:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM virtual_hedge_trades WHERE book_name=? ORDER BY created_at DESC, rowid DESC", (book,)).fetchall()]
