import { useEffect, useState } from "react";
import { send } from "../api";
import type { Ctx } from "../App";
import { Badge, Card, Err, Explain, fmt, Kpi, Loading, Signed, UND, usd, useAsync } from "../ui";

export default function Portfolio({ snap, nPaths, seed, bookVer, bumpBook }: Ctx) {
  const risk = useAsync();
  const [err, setErr] = useState<any>(null);
  const load = () => risk.run(() => send("/risk/portfolio", { snapshot_id: snap.snapshot_id, n_paths: nPaths, seed }));
  useEffect(() => { load(); }, [snap.snapshot_id, nPaths, seed, bookVer]);
  const setQty = (id: string, v: string) => { if (v === "" || isNaN(Number(v))) return; setErr(null); send(`/book/positions/${id}`, { signed_quantity: Number(v) }, "PATCH").then(bumpBook).catch(setErr); };
  const r = risk.data, t = r?.totals;
  return (
    <>
      <h1>④ 장부 Portfolio & Risk</h1>
      <p className="sub">가상 장부의 포지션별 평가금액과 기초자산별 위험 합계</p>
      <Explain goal={["부호(매수 +, 매도 -)와 승수를 반영해 포지션 위험을 합산", "서로 다른 기초자산의 Delta는 따로 관리"]}
        read={["Delta 합계가 -55주면 해당 ETF 55주를 매도한 것과 같은 노출", "평가금액은 현재 모형 가치이며 손익이 아님", "노트는 Theta를 제공하지 않아 Theta 합계는 부분 집계"]}
        missing={["환율, 신용, 유동성, 모형 위험, 교차 감마", "거래 한도와 규제 자본"]}
        interview="상품 하나의 위험이 작아 보여도 전체 포지션의 부호와 계약 승수를 합치면 회사가 지는 위험이 달라집니다. 그래서 같은 기준으로 포지션을 평가하고 기초자산별로 합산했습니다." />
      <Err e={err} /><Err e={risk.error} />{risk.loading && <Loading text="장부 평가 중 (노트는 Monte Carlo)" />}
      {r && <>
        <div className="grid g4">
          <Kpi label="장부 평가금액 합계" badge="MODEL ESTIMATE" value={<Signed v={t.mtm} />} sub="손익이 아닌 현재 모형 가치" />
          {UND.map((u) => <Kpi key={u} label={`${u} 순 Delta`} value={<Signed v={t.delta[u]} unit="주" />} sub={<>달러 Delta <Signed v={t.dollar_delta[u]} d={0} /></>} />)}
          {UND.map((u) => <Kpi key={u + "v"} label={`${u} Vega`} value={<Signed v={t.vega[u]} />} sub="변동성 +1%p 시" />)}
          <Kpi label="Theta (부분 집계)" value={<Signed v={t.theta_partial} />} sub="1일 경과 시. 노트 제외" />
        </div>
        <Card title="포지션별 평가와 위험" right={<><Badge label={r.data.mode} /> <span className="mut">입력 기준일 {r.data.as_of}</span></>}>
          <div className="tw"><table>
            <thead><tr><th>상품</th><th>수량(+매수/-매도)</th><th>이론가/개</th><th>평가금액</th><th>SPY Delta</th><th>QQQ Delta</th><th>SPY Vega</th><th>QQQ Vega</th><th>Theta/일</th><th>Rho</th><th className="l">모형</th></tr></thead>
            <tbody>
              {r.rows.map((x: any) => <tr key={x.position_id}>
                <td title={x.warnings.join(" / ")}>{x.name}</td>
                <td><input className="q" type="number" defaultValue={x.signed_quantity} onBlur={(e) => Number(e.target.value) !== x.signed_quantity && setQty(x.position_id, e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} /></td>
                <td>{usd(x.unit_price)}</td><td><Signed v={x.mtm} /></td>
                <td><Signed v={x.delta.SPY} unit="" /></td><td><Signed v={x.delta.QQQ} unit="" /></td>
                <td><Signed v={x.vega.SPY} /></td><td><Signed v={x.vega.QQQ} /></td>
                <td><Signed v={x.theta} /></td><td><Signed v={x.rho} /></td><td className="l">{x.model}</td></tr>)}
              <tr style={{ fontWeight: 600 }}><td>합계</td><td></td><td></td><td><Signed v={t.mtm} /></td><td><Signed v={t.delta.SPY} unit="" /></td><td><Signed v={t.delta.QQQ} unit="" /></td>
                <td><Signed v={t.vega.SPY} /></td><td><Signed v={t.vega.QQQ} /></td><td><Signed v={t.theta_partial} /> <span className="mut">(부분)</span></td><td><Signed v={t.rho} /></td><td></td></tr>
            </tbody>
          </table></div>
          <p className="note">수량을 고친 뒤 Enter를 누르면 다시 계산함. Delta 단위는 주식 환산 수량, Vega는 변동성 +1%p, Rho는 금리 +100bp 기준 USD. 상품명에 마우스를 올리면 평가상 유의 사항이 표시됨.</p>
        </Card>
        <div className="grid g2" style={{ marginTop: 12 }}>
          <Card title="기초자산 1% 변동 시 손익 근사 (자산별 단독 충격)">
            <table><thead><tr><th>기초자산</th><th>현물가</th><th>Gamma 합계</th><th>Delta만</th><th>Delta + Gamma</th></tr></thead><tbody>
              {UND.map((u) => <tr key={u}><td>{u} +1%</td><td>{usd(r.spots[u])}</td><td>{fmt(t.gamma[u], 3)}</td><td><Signed v={t.one_pct_move[u].delta_only} /></td><td><Signed v={t.one_pct_move[u].delta_gamma} /></td></tr>)}
            </tbody></table>
            <p className="note">재평가 손익과의 비교는 스트레스 화면에서 확인. 두 자산이 함께 움직일 때의 교차 감마는 포함하지 않음.</p>
          </Card>
          <Card title="유의 사항">
            <ul className="note" style={{ marginTop: 0 }}>{r.notes.map((n: string, k: number) => <li key={k}>{n}</li>)}<li>측정하지 않는 위험: {r.unmeasured_risks.join(", ")}</li>
              <li>노트 평가금액의 표준오차: {usd(r.rows.find((x: any) => x.model === "MC-GBM")?.detail.mtm_std_error)} · 경로 {r.n_paths.toLocaleString()}개 · 시드 {r.seed}</li><li>평가 기록 번호 {r.valuation_id}</li></ul>
          </Card>
        </div>
      </>}
    </>
  );
}
