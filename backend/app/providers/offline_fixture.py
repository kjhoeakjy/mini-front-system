"""오프라인용 가상 자료. 실제 시장 수치가 아니다."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_demo.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
