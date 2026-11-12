"""FRED 미국 국채 고정만기 수익률(DGS3MO, DGS1, DGS2).

FRED_API_KEY가 있으면 공식 API를, 없으면 공개 CSV 내려받기 주소를 사용한다.
고정만기 수익률은 무위험 할인곡선이 아니며 평탄한 연속복리 금리의 근사로 쓴다.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import httpx

from .base import ProviderError

SERIES = {"DGS3MO": 0.25, "DGS1": 1.0, "DGS2": 2.0}


def _last_valid(pairs: list) -> tuple[str, float]:
    for d, v in reversed(pairs):
        try:
            return d, float(v)
        except (TypeError, ValueError):
            continue
    raise ProviderError("유효한 관측값이 없음")


def fetch_rate(series: str, timeout: float = 15.0) -> dict:
    key = os.environ.get("FRED_API_KEY", "").strip()
    start = (date.today() - timedelta(days=30)).isoformat()
    try:
        if key:
            r = httpx.get("https://api.stlouisfed.org/fred/series/observations",
                          params={"series_id": series, "api_key": key, "file_type": "json", "observation_start": start}, timeout=timeout)
            r.raise_for_status()
            pairs = [(o["date"], o["value"]) for o in r.json()["observations"]]
            src = "FRED API"
        else:
            r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series, "cosd": start},
                          timeout=timeout, follow_redirects=True)
            r.raise_for_status()
            lines = r.text.strip().splitlines()[1:]
            pairs = [tuple(x.split(",")[:2]) for x in lines if "," in x]
            src = "FRED 공개 CSV"
        obs_date, pct = _last_valid(pairs)
    except ProviderError:
        raise
    except Exception as e:
        # 키가 포함된 주소가 노출되지 않도록 예외 종류만 전달한다.
        raise ProviderError(f"{series} 금리 수집 실패: {type(e).__name__}")
    return {"series": series, "tenor_years": SERIES[series], "value_pct": pct, "value": pct / 100.0, "observed_date": obs_date,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": src, "unit": "연율 소수",
            "approximation": True}


def fetch_all() -> list:
    return [fetch_rate(s) for s in SERIES]
