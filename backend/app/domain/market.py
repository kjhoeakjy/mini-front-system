"""평가에 쓰는 시장 입력. 계약 조건과 분리해 관리한다."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

UNDERLYINGS = ("SPY", "QQQ")
LABELS = ("REAL MARKET DATA", "CACHED REAL SNAPSHOT", "MANUAL SCENARIO", "SYNTHETIC DEMO", "MODEL ESTIMATE")
MIN_VOL = 0.01


@dataclass(frozen=True)
class MarketInputs:
    as_of: date
    spots: dict
    vols: dict
    divs: dict
    curve: tuple      # ((만기 연수, 연속복리 금리), ...) 만기 오름차순
    corr: float

    def rate(self, T: float) -> float:
        """만기 T의 금리. 관측 만기 사이는 선형 보간, 바깥은 가장 가까운 값을 쓴다(근사)."""
        pts = sorted(self.curve)
        if not pts:
            raise ValueError("금리 입력이 없음")
        if T <= pts[0][0]:
            return pts[0][1]
        if T >= pts[-1][0]:
            return pts[-1][1]
        for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
            if t0 <= T <= t1:
                return r0 + (r1 - r0) * (T - t0) / (t1 - t0)
        return pts[-1][1]

    def shocked(self, spot_pct: dict | None = None, vol_pts: float = 0.0, rate_bp: float = 0.0,
                corr_shift: float = 0.0) -> tuple["MarketInputs", list]:
        """충격을 적용한 새 입력과 경고 목록. 계약 조건(기준가, 행사가)은 건드리지 않는다."""
        warnings = []
        spot_pct = spot_pct or {}
        spots = {u: s * (1.0 + spot_pct.get(u, 0.0) / 100.0) for u, s in self.spots.items()}
        vols = {}
        for u, v in self.vols.items():
            nv = v + vol_pts / 100.0
            if nv < MIN_VOL:
                warnings.append(f"{u} 변동성이 하한 {MIN_VOL:.0%} 미만이 되어 하한으로 대체함")
                nv = MIN_VOL
            vols[u] = nv
        curve = tuple((t, r + rate_bp / 10000.0) for t, r in self.curve)
        corr = self.corr + corr_shift
        if not (-0.999 <= corr <= 0.999):
            warnings.append("상관계수가 허용 범위를 벗어나 경계값으로 대체함")
            corr = max(-0.999, min(0.999, corr))
        return replace(self, spots=spots, vols=vols, curve=curve, corr=corr), warnings


def inputs_from_snapshot(snap: dict) -> MarketInputs:
    i = snap["inputs"]
    return MarketInputs(
        as_of=date.fromisoformat(snap["as_of"]),
        spots={u: float(i["spots"][u]["value"]) for u in UNDERLYINGS},
        vols={u: float(i["vols"][u]["value"]) for u in UNDERLYINGS},
        divs={u: float(i["divs"][u]["value"]) for u in UNDERLYINGS},
        curve=tuple((float(p["tenor_years"]), float(p["value"])) for p in i["curve"]),
        corr=float(i["corr"]["value"]),
    )
