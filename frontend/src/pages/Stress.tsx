import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, Explain, Field, fmt, Loading, Signed, usd, useAsync } from "../ui";

export default function Stress({ snap, nPaths, seed, bookVer }: Ctx) {
  const st = useAsync(), hm = useAsync(), cu = useAsync();
  const [open, setOpen] = useState<string | null>(null);
  const [c, setC] = useState<any>({ spy: -10, qqq: -10, vol: 5, rate: 0, corr: 0 });
  const base = { snapshot_id: snap.snapshot_id, n_paths: nPaths, seed };
  useEffect(() => { st.run(() => send("/risk/stress", base)); hm.setData(null); cu.setData(null); }, [snap.snapshot_id, nPaths, seed, bookVer]);
  const custom = () => cu.run(() => send("/risk/stress", { ...base, scenarios: [{ id: "custom", name: "사용자 정의", spot_pct: { SPY: c.spy || 0, QQQ: c.qqq || 0 }, vol_pts: c.vol || 0, rate_bp: c.rate || 0, corr_shift: c.corr || 0 }] }));
  const s = st.data;
  const Row = ({ x, pos }: any) => <>
    <tr onClick={() => setOpen(open === x.id ? null : x.id)} style={{ cursor: "pointer" }}>
      <td>{x.name}</td><td><Signed v={x.pnl_full_reprice} /></td><td><Signed v={x.approx.delta_only} /></td><td><Signed v={x.approx.delta_gamma} /></td><td><Signed v={x.approx.all_greeks} /></td>
      <td><Signed v={x.approx.all_greeks - x.pnl_full_reprice} /></td><td>{usd(x.base_value)}</td><td>{usd(x.shocked_value)}</td></tr>
    {open === x.id && <tr><td colSpan={8} className="wrap">포지션별 기여: {pos.map((p: any, k: number) => <span key={p.id} style={{ marginRight: 14 }}>{p.name} <Signed v={x.by_position[k]} /></span>)}{x.warnings.length > 0 && <span className="warn"> · {x.warnings.join(", ")}</span>}</td></tr>}
  </>;
  const mx = hm.data?.available ? Math.max(...hm.data.change.flat().map((v: number) => Math.abs(v)), 1) : 1;
  return (
    <>
      <h1>⑥ 스트레스 Stress & Explain</h1>
      <p className="sub">시장 입력에 충격을 주고 장부 전체를 다시 평가한 손익. 손실 확률 예측이 아닌 가정 분석</p>
      <Explain goal={["충격 손익 = 충격 후 평가금액 - 기준 평가금액", "Greeks 근사와 재평가의 차이로 비선형성 확인", "델타 헤지 후에도 큰 충격과 변동성 충격에는 손익이 남는 점 확인"]}
        read={["행을 누르면 포지션별 기여가 표시됨", "근사 오차가 큰 시나리오는 비선형성이 큰 경우", "노트는 기준과 충격을 같은 난수로 평가해 차이의 잡음을 줄임"]}
        missing={["VaR·기대손실 같은 확률 기반 지표", "충격 후 유동성 악화와 헤지 비용 증가", "변동성과 주가가 함께 움직이는 관계"]}
        interview="수익률 예측, 위험중립 평가, 스트레스 테스트, 헤지는 서로 다른 기능입니다. 이 화면은 예측이 아니라 가정한 충격에서 장부 가치가 얼마나 바뀌는지를 같은 모형으로 다시 계산해 보여줍니다." />
      <Err e={st.error} />{st.loading && <Loading text="시나리오 재평가 중" />}
      {s && <>
        <Card title="기본 시나리오" right={<><Badge label="MODEL ESTIMATE" /> <span className="mut">입력 {s.data.mode} · {s.data.as_of}</span></>}>
          <div className="tw"><table>
            <thead><tr><th>시나리오</th><th>재평가 손익</th><th>Delta만</th><th>Delta + Gamma</th><th>Greeks 전체 근사</th><th>근사 오차</th><th>기준 평가금액</th><th>충격 후 평가금액</th></tr></thead>
            <tbody>{s.scenarios.map((x: any) => <Row key={x.id} x={x} pos={s.positions} />)}</tbody>
          </table></div>
          <p className="note">{s.definition}. 평가금액 수준의 Monte Carlo 95% 오차 한계 ±{usd(s.mc_noise_95)}. 상관계수 시나리오는 Greeks 근사에 포함되지 않아 0으로 표시됨.</p>
          <ResponsiveContainer width="100%" height={240}><BarChart data={s.scenarios.map((x: any) => ({ name: x.name, 재평가: x.pnl_full_reprice, "Delta만": x.approx.delta_only }))}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="name" {...axis} interval={0} tick={{ fontSize: 10 }} /><YAxis {...axis} width={60} tickFormatter={(v) => fmt(v, 0)} /><ReferenceLine y={0} stroke="var(--mut)" />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} /><Legend /><Bar dataKey="재평가" fill="var(--chart1)" isAnimationActive={false} /><Bar dataKey="Delta만" fill="var(--chart2)" isAnimationActive={false} />
          </BarChart></ResponsiveContainer>
        </Card>
        <div className="grid g2" style={{ marginTop: 12 }}>
          <Card title="사용자 정의 시나리오" right={<Badge label="MANUAL SCENARIO" />}>
            <div className="form">
              <Field label="SPY 현물 %" value={c.spy} onChange={(v) => setC({ ...c, spy: v })} /><Field label="QQQ 현물 %" value={c.qqq} onChange={(v) => setC({ ...c, qqq: v })} />
              <Field label="변동성 %p" value={c.vol} onChange={(v) => setC({ ...c, vol: v })} /><Field label="금리 bp" value={c.rate} onChange={(v) => setC({ ...c, rate: v })} />
              <Field label="상관계수 변화" value={c.corr} step={0.05} onChange={(v) => setC({ ...c, corr: v })} />
            </div>
            <div className="row"><button className="b" onClick={custom} disabled={cu.loading}>재평가</button></div>
            <Err e={cu.error} />{cu.loading && <Loading />}
            {cu.data && <div className="tw"><table><thead><tr><th>시나리오</th><th>재평가 손익</th><th>Delta만</th><th>Delta + Gamma</th><th>Greeks 전체 근사</th><th>근사 오차</th><th>기준</th><th>충격 후</th></tr></thead>
              <tbody>{cu.data.scenarios.map((x: any) => <Row key={x.id} x={x} pos={cu.data.positions} />)}</tbody></table></div>}
          </Card>
          <Card title="SPY·QQQ 충격 조합별 노트 이론가 변화 (투자자 1개, USD)" right={<button className="b sec" onClick={() => hm.run(() => send("/risk/heatmap", { snapshot_id: snap.snapshot_id, seed }))} disabled={hm.loading}>계산</button>}>
            {hm.loading && <Loading />}<Err e={hm.error} />
            {hm.data?.available && <>
              <table className="heat"><thead><tr><th>QQQ \ SPY</th>{hm.data.shocks_pct.map((x: number) => <th key={x} style={{ textAlign: "center" }}>{x > 0 ? "+" : ""}{x}%</th>)}</tr></thead>
                <tbody>{hm.data.change.map((row: number[], i2: number) => <tr key={i2}><td>{hm.data.shocks_pct[i2] > 0 ? "+" : ""}{hm.data.shocks_pct[i2]}%</td>
                  {row.map((v, j) => <td key={j} style={{ background: `color-mix(in srgb, ${v >= 0 ? "var(--pos)" : "var(--neg)"} ${Math.round(Math.min(1, Math.abs(v) / mx) * 45)}%, transparent)` }}>{v > 0 ? "+" : ""}{fmt(v, 0)}</td>)}</tr>)}</tbody></table>
              <p className="note">기준 이론가 {usd(hm.data.base_price)} (표준오차 {fmt(hm.data.std_error)}) · 경로 {hm.data.n_paths.toLocaleString()}개. 한 자산만 하락해도 가치가 크게 떨어짐. 두 자산 중 낮은 쪽이 상환을 결정하기 때문임. 발행자(매도) 손익은 부호가 반대.</p>
            </>}
            {hm.data && !hm.data.available && <p className="note warn">{hm.data.reason}</p>}
            {!hm.data && !hm.loading && <p className="note">계산을 누르면 5 × 5 격자를 같은 난수로 평가함.</p>}
          </Card>
        </div>
      </>}
    </>
  );
}
