import type { Deal } from "../App";
import { fmt, pct, usd } from "../ui";

/** 모든 단계 상단에 표시하는 현재 거래 요약. 계약 조건은 거래 시점에 확정된 값이다. */
export default function DealSummary({ deal, opt, det, shares, days, start }: { deal: Deal; opt: any; det: any; shares: number; days: number; start: (s: "base" | "market") => void }) {
  const i = deal.snap.inputs, s = opt.spec;
  const items: [string, string][] = [
    ["상품", "SPY 유럽형 콜 (가상 장외)"], ["포지션", `매도 ${fmt(Math.abs(opt.signed_quantity), 0)}계약 (${fmt(s.multiplier, 0)}주)`],
    ["행사가", usd(s.strike)], ["만기", `${s.expiry} (${days}일)`], ["SPY 현물가", usd(i.spots.SPY.value)],
    ["변동성", pct(det.sigma, 1)], ["금리", pct(det.r)], ["배당수익률", pct(det.q, 1)], ["현물 보유", `${fmt(shares, 0)}주`],
  ];
  return (
    <div className="deal">
      <div className="kvs">{items.map(([k, v]) => <span key={k} className="kv"><span>{k}</span>{v}</span>)}</div>
      <div className="row" style={{ marginTop: 0 }}>
        <span className="seg">
          <button className={deal.source === "base" ? "on" : ""} onClick={() => deal.source !== "base" && start("base")}>기준 시나리오</button>
          <button className={deal.source === "market" ? "on" : ""} onClick={() => deal.source !== "market" && start("market")}>시장 데이터</button>
        </span>
        <button className="b sec" onClick={() => start(deal.source)}>초기화</button>
      </div>
    </div>
  );
}
