import { useEffect, useState } from "react";
import { send } from "../api";
import type { Ctx } from "../App";
import { Badge, Card, Err, fmt, Kpi, Loading, Signed, UND, usd, useAsync } from "../ui";

export default function Portfolio({ snap, nPaths, seed, bookVer, bumpBook }: Ctx) {
  const risk = useAsync();
  const [err, setErr] = useState<any>(null);
  const load = () => risk.run(() => send("/risk/portfolio", { snapshot_id: snap.snapshot_id, n_paths: nPaths, seed }));
  useEffect(() => { load(); }, [snap.snapshot_id, nPaths, seed, bookVer]);
  const setQty = (id: string, v: string) => { if (v === "" || isNaN(Number(v))) return; setErr(null); send(`/book/positions/${id}`, { signed_quantity: Number(v) }, "PATCH").then(bumpBook).catch(setErr); };
  const r = risk.data, t = r?.totals;
  return (
    <>
      <h1>④ 포트폴리오 위험</h1>
      <Err e={err} /><Err e={risk.error} />{risk.loading && <Loading text="포트폴리오 평가 중" />}
      {r && <>
        <div className="grid g4">
          <Kpi label="포트폴리오 평가금액" value={<Signed v={t.mtm} />} />
          {UND.map((u) => <Kpi key={u} label={`${u} 순 Delta`} value={<Signed v={t.delta[u]} unit="주" />} sub={<>달러 Delta <Signed v={t.dollar_delta[u]} d={0} /></>} />)}
          {UND.map((u) => <Kpi key={u + "v"} label={`${u} Vega`} value={<Signed v={t.vega[u]} />} sub="변동성 +1%p" />)}
          <Kpi label="Theta (노트 제외)" value={<Signed v={t.theta_partial} />} sub="1일 경과" />
        </div>
        <Card title="포지션별 평가금액 · 민감도">
          <div className="tw"><table>
            <thead><tr><th>상품</th><th>수량</th><th>단위 이론가</th><th>평가금액</th><th>SPY Delta</th><th>QQQ Delta</th><th>SPY Vega</th><th>QQQ Vega</th><th>Theta/일</th><th>Rho</th><th className="l">모형</th></tr></thead>
            <tbody>
              {r.rows.map((x: any) => <tr key={x.position_id}>
                <td title={x.warnings.join(" / ")}>{x.name}</td>
                <td><input className="q" type="number" defaultValue={x.signed_quantity} onBlur={(e) => Number(e.target.value) !== x.signed_quantity && setQty(x.position_id, e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} /></td>
                <td>{usd(x.unit_price)}</td><td><Signed v={x.mtm} /></td>
                <td><Signed v={x.delta.SPY} unit="" /></td><td><Signed v={x.delta.QQQ} unit="" /></td>
                <td><Signed v={x.vega.SPY} /></td><td><Signed v={x.vega.QQQ} /></td>
                <td><Signed v={x.theta} /></td><td><Signed v={x.rho} /></td><td className="l">{x.model}</td></tr>)}
              <tr style={{ fontWeight: 600 }}><td>합계</td><td></td><td></td><td><Signed v={t.mtm} /></td><td><Signed v={t.delta.SPY} unit="" /></td><td><Signed v={t.delta.QQQ} unit="" /></td>
                <td><Signed v={t.vega.SPY} /></td><td><Signed v={t.vega.QQQ} /></td><td><Signed v={t.theta_partial} /> <span className="mut">(노트 제외)</span></td><td><Signed v={t.rho} /></td><td></td></tr>
            </tbody>
          </table></div>
        </Card>
        <div className="grid g2" style={{ marginTop: 12 }}>
          <Card title="기초자산 +1% 손익 근사 (단독 충격)">
            <table><thead><tr><th>기초자산</th><th>현물가</th><th>Gamma</th><th>Delta 근사</th><th>Delta + Gamma 근사</th></tr></thead><tbody>
              {UND.map((u) => <tr key={u}><td>{u}</td><td>{usd(r.spots[u])}</td><td>{fmt(t.gamma[u], 3)}</td><td><Signed v={t.one_pct_move[u].delta_only} /></td><td><Signed v={t.one_pct_move[u].delta_gamma} /></td></tr>)}
            </tbody></table>
          </Card>
        </div>
      </>}
    </>
  );
}
