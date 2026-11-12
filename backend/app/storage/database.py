"""로컬 SQLite 저장소. 외부로 전송하는 자료는 없다."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("MINI_FO_DB", Path(__file__).resolve().parents[2] / "data" / "app.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_snapshots (id TEXT PRIMARY KEY, created_at TEXT, as_of TEXT, mode TEXT, parent_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS instruments (id TEXT PRIMARY KEY, instrument_type TEXT, name TEXT, version INTEGER, spec TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS positions (id TEXT PRIMARY KEY, instrument_id TEXT, book_name TEXT, signed_quantity REAL, sort_order INTEGER, entry_cost REAL);
CREATE TABLE IF NOT EXISTS valuation_runs (id TEXT PRIMARY KEY, created_at TEXT, kind TEXT, snapshot_id TEXT, model_version TEXT, seed INTEGER, n_paths INTEGER, inputs TEXT, outputs TEXT, warnings TEXT);
CREATE TABLE IF NOT EXISTS virtual_hedge_trades (id TEXT PRIMARY KEY, created_at TEXT, underlying TEXT, shares REAL, price REAL, cost REAL, snapshot_id TEXT);
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        if "book_name" not in [r[1] for r in c.execute("PRAGMA table_info(virtual_hedge_trades)")]:
            c.execute("ALTER TABLE virtual_hedge_trades ADD COLUMN book_name TEXT DEFAULT 'DEMO'")
        yield c
        c.commit()
    finally:
        c.close()


def log_valuation(kind: str, inputs: dict, outputs: dict, snapshot_id: str | None = None, model_version: str = "",
                  seed: int | None = None, n_paths: int | None = None, warnings: list | None = None) -> str:
    vid = new_id("val")
    with conn() as c:
        c.execute("INSERT INTO valuation_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (vid, now_utc(), kind, snapshot_id, model_version, seed, n_paths,
                   json.dumps(inputs, default=str), json.dumps(outputs, default=str), json.dumps(warnings or [])))
    return vid


def get_valuation(vid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM valuation_runs WHERE id=?", (vid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("inputs", "outputs", "warnings"):
        d[k] = json.loads(d[k])
    return d
