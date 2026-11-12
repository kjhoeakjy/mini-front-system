"""실제 원자료(시세·금리)를 받아 fixtures/real_raw.json으로 저장한다. 정적 배포본에 함께 싣는 용도."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.market import UNDERLYINGS  # noqa: E402
from app.providers import market_yahoo, rates_fred  # noqa: E402
from app.providers.base import ProviderError  # noqa: E402
from app.services.snapshot_service import DEFAULT_MANUAL_RATE  # noqa: E402

tickers = {u: market_yahoo.fetch_ticker(u) for u in UNDERLYINGS}
try:
    rates, real = rates_fred.fetch_all(), True
except ProviderError as e:
    print("금리 수집 실패:", e)
    rates, real = [{"series": s, "tenor_years": t, "value_pct": DEFAULT_MANUAL_RATE * 100, "value": DEFAULT_MANUAL_RATE, "observed_date": None,
                    "fetched_at": None, "source": "수동 가정값", "unit": "연율 소수", "approximation": True} for s, t in rates_fred.SERIES.items()], False
out = Path(__file__).resolve().parents[1] / "fixtures" / "real_raw.json"
out.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tickers": tickers, "rates": rates,
                           "rates_real": real}, ensure_ascii=False), encoding="utf-8")
print("저장:", out)
