"""오프라인용 가상 자료. 실제 시장 수치가 아니다."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_demo.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


BUNDLED_REAL = FIXTURE.parent / "real_raw.json"


def load_bundled_real() -> dict | None:
    """배포 시점에 수집해 함께 올린 실제 원자료. 없으면 None."""
    if not BUNDLED_REAL.exists():
        return None
    return json.loads(BUNDLED_REAL.read_text(encoding="utf-8"))
