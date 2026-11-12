"""가상 시세 자료 생성. 난수 시드를 고정한 상관 GBM 경로이며 실제 시세가 아니다."""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

rng = np.random.default_rng(20250630)
n, rho = 520, 0.85
end = date(2025, 6, 30)
days = []
d = end
while len(days) < n:
    if d.weekday() < 5:
        days.append(d)
    d -= timedelta(days=1)
days.reverse()
z = rng.standard_normal((2, n - 1))
z2 = rho * z[0] + math.sqrt(1 - rho ** 2) * z[1]
out = {}
for name, zz, vol, mu, last, q in (("SPY", z[0], 0.16, 0.08, 500.0, 0.012), ("QQQ", z2, 0.22, 0.10, 400.0, 0.006)):
    lr = (mu - 0.5 * vol ** 2) / 252 + vol / math.sqrt(252) * zz
    path = np.exp(np.concatenate([[0.0], np.cumsum(lr)]))
    path = path / path[-1] * last
    out[name] = {"ticker": name, "history": [{"date": dd.isoformat(), "close": round(float(p), 2), "adj_close": round(float(p), 2)}
                                             for dd, p in zip(days, path)],
                 "last_bar_date": end.isoformat(), "dividend_yield": q, "source": "SYNTHETIC (seeded GBM)",
                 "fetched_at": None, "currency": "USD", "quality_flags": ["가상 자료"]}
rates = [{"series": s, "tenor_years": t, "value_pct": v, "value": v / 100, "observed_date": end.isoformat(), "fetched_at": None,
          "source": "SYNTHETIC", "unit": "연율 소수", "approximation": True}
         for s, t, v in (("DGS3MO", 0.25, 4.2), ("DGS1", 1.0, 4.0), ("DGS2", 2.0, 3.9))]
Path(__file__).resolve().parents[1].joinpath("fixtures", "synthetic_demo.json").write_text(
    json.dumps({"description": "가상 자료. 실제 시장 수치가 아님", "tickers": out, "rates": rates}, ensure_ascii=False), encoding="utf-8")
print("ok")
