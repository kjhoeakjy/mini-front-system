import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, Explain, Field, fmt, Kpi, Loading, Signed, usd, useAsync, useDebounced } from "../ui";

const HELP: Record<string, [string, string]> = {
  delta_shares: ["Delta", "기초자산 가격이 $1 오를 때 포지션 가치가 변하는 금액. 같은 숫자의 주식을 보유한 것과 같은 노출이므로 헤지 주식 수의 기준이 됨."],
  gamma_per_usd: ["Gamma", "기초자산 가격이 $1 오를 때 Delta가 변하는 양. 0이 아니면 가격이 움직일 때마다 헤지 수량을 다시 맞춰야 함."],
  vega_per_1volpt_usd: ["Vega", "변동성이 1%p 오를 때 포지션 가치가 변하는 금액. 옵션 매수는 양수, 매도는 음수."],
  theta_per_calendar_day_usd: ["Theta", "다른 조건이 같을 때 하루가 지나면 포지션 가치가 변하는 금액. 옵션 매수는 대체로 음수."],
  rho_per_100bp_usd: ["Rho", "금리가 1%p(100bp) 오를 때 포지션 가치가 변하는 금액."],
};

export default function OptionLab({ snap }: Ctx) {
  const i = snap.inputs;
  const init = (u: string) => ({ underlying: u, option_type: u === "SPY" ? "CALL" : "PUT", side: u === "SPY" ? -1 : 1, contracts: 1, spot: i.spots[u].value, strike: i.spots[u].value,
    days: u === "SPY" ? 90 : 180, r: +(i.curve[0].value * 100).toFixed(2), q: +(i.divs[u].value * 100).toFixed(2), vol: +(i.vols[u].value * 100).toFixed(2), shock: 5 });
  const [f, setF] = useState<any>(init("SPY"));
  const [help, setHelp] = useState<string | null>(null);
  const [edited, setEdited] = useState(false);
  const res = useAsync();
  const d = useDebounced(f);
  useEffect(() => { setF(init(f.underlying)); setEdited(false); }, [snap.snapshot_id]);
  const set = (k: string, v: any) => { setF({ ...f, [k]: v }); setEdited(true); };

  useEffect(() => {
    if ([d.spot, d.strike, d.days, d.r, d.q, d.vol, d.contracts].some((x) => x === "" || x === null)) return;
    const val = new Date(snap.as_of + "T00:00:00Z");
    const exp = new Date(val.getTime() + d.days * 86400000);
    res.run(() => send("/pricing/european", { underlying: d.underlying, option_type: d.option_type, spot: d.spot, strike: d.strike, valuation_date: snap.as_of,
      expiry: exp.toISOString().slice(0, 10), risk_free_rate: d.r / 100, dividend_yield: d.q / 100, volatility: d.vol / 100, multiplier: 100,
      signed_quantity: d.side * d.contracts, input_mode: edited ? "MANUAL SCENARIO" : snap.mode, spot_shock_pct: d.shock || 0, curves: true }));
  }, [JSON.stringify(d), snap.snapshot_id]);

  const r = res.data, g = r?.greeks_position, sc = r?.shock_compare;
  return (
    <>
      <h1>② 옵션 Option Pricing Lab</h1>
      <p className="sub">가상 장외 유럽형 옵션의 가격과 Greeks. 입력을 바꾸면 같은 엔진으로 즉시 다시 계산함</p>
      <Explain goal={["옵션 가격을 결정하는 여섯 입력(현물가, 행사가, 잔존만기, 금리, 배당, 변동성) 확인", "매수·매도에 따라 Greeks 부호가 반대가 되는 점 확인", "Delta 근사와 재평가 손익의 차이 확인"]}
        read={["포지션 Greeks는 주당 값 × 승수 100 × 부호 있는 계약 수", "Delta가 -55면 주식 55주를 매도한 것과 같은 노출이므로 55주 매수로 상쇄"]}
        missing={["상장 SPY·QQQ 옵션은 미국형이므로 이 값과 다름", "행사가·만기별로 다른 변동성(스마일)", "이산 배당, 조기 행사"]}
        interview="옵션 가치는 기초자산 가격, 행사가, 잔존만기, 금리, 배당, 변동성으로 정해집니다. 이 화면은 유럽형 가정에서 그 관계를 계산하고, 델타는 가격 민감도, 감마는 델타의 변화, 베가는 변동성, 세타는 시간, 로는 금리 민감도임을 숫자로 보여줍니다." />
      <div className="grid g2">
        <Card title="계약과 시장 입력" right={<Badge label={edited ? "MANUAL SCENARIO" : snap.mode} />}>
          <div className="form">
            <label>기초자산<select value={f.underlying} onChange={(e) => { setF(init(e.target.value)); setEdited(false); }}><option>SPY</option><option>QQQ</option></select></label>
            <label>옵션 종류<select value={f.option_type} onChange={(e) => set("option_type", e.target.value)}><option value="CALL">콜 CALL</option><option value="PUT">풋 PUT</option></select></label>
            <label>포지션<select value={f.side} onChange={(e) => set("side", Number(e.target.value))}><option value={1}>매수 (long)</option><option value={-1}>매도 (short)</option></select></label>
            <Field label="계약 수" value={f.contracts} onChange={(v) => set("contracts", v)} />
            <Field label="현물가 S" value={f.spot} onChange={(v) => set("spot", v)} />
            <Field label="행사가 K" value={f.strike} onChange={(v) => set("strike", v)} />
            <Field label="잔존만기 (일)" value={f.days} onChange={(v) => set("days", v)} />
            <Field label="금리 r %" value={f.r} step={0.1} onChange={(v) => set("r", v)} />
            <Field label="배당률 q %" value={f.q} step={0.1} onChange={(v) => set("q", v)} />
            <Field label="변동성 σ %" value={f.vol} step={0.5} onChange={(v) => set("vol", v)} />
          </div>
          <div className="row">
            <button className="b sec" onClick={() => set("spot", +(f.spot * 1.05).toFixed(2))}>현물가 +5%</button>
            <button className="b sec" onClick={() => set("spot", +(f.spot * 0.95).toFixed(2))}>현물가 -5%</button>
            <button className="b sec" onClick={() => set("vol", f.vol + 5)}>변동성 +5%p</button>
            <button className="b sec" onClick={() => { setF(init(f.underlying)); setEdited(false); }}>스냅샷 값으로 되돌리기</button>
          </div>
          <p className="note">승수 100주/계약. 값을 수정하면 표기가 MANUAL SCENARIO로 바뀜.</p>
        </Card>
        <div>
          <Err e={res.error} />{res.loading && <Loading />}
          {r && <>
            <div className="grid g3" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
              <Kpi label="이론가 (주당)" badge="MODEL ESTIMATE" value={usd(r.model_price_per_share_usd, 4)} sub="BSM 유럽형" />
              <Kpi label="이론가 (계약당)" value={usd(r.model_price_per_contract_usd)} sub="주당 × 100" />
              <Kpi label="포지션 평가금액" value={<Signed v={r.signed_position_mtm_usd} />} sub={f.side > 0 ? "매수: 자산(+)" : "매도: 부채(-)"} />
            </div>
            <Card title="포지션 Greeks" right={<Badge label="MODEL ESTIMATE" />}>
              <table><thead><tr><th>지표</th><th>값</th><th className="l">단위</th></tr></thead><tbody>
                {Object.keys(HELP).map((k) => <tr key={k}><td>{HELP[k][0]}<button className="help" onClick={() => setHelp(help === k ? null : k)}>?</button></td>
                  <td><Signed v={g[k]} d={k === "gamma_per_usd" ? 4 : 2} unit={k === "delta_shares" ? "주" : k === "gamma_per_usd" ? "" : "$"} /></td><td className="wrap">{r.units[k]}</td></tr>)}
              </tbody></table>
              {help && <div className="helpbox"><b>{HELP[help][0]}</b> {HELP[help][1]}<br />현재 값 해석: {help === "delta_shares" ? `기초자산이 $1 오르면 이 포지션은 약 ${usd(g[help])} 변함. Delta를 0으로 만들려면 주식 ${fmt(Math.abs(r.hedge_shares_for_delta_neutral), 1)}주 ${r.hedge_shares_for_delta_neutral > 0 ? "매수" : "매도"}.` : `해당 요인이 단위만큼 변하면 약 ${fmt(g[help], help === "gamma_per_usd" ? 4 : 2)} 변함.`}</div>}
            </Card>
          </>}
        </div>
      </div>
      {r && sc && <Card title="같은 가격 충격의 손익을 세 가지 방법으로 계산" right={<span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><span className="mut">충격 %</span><input className="q" type="number" value={f.shock} onChange={(e) => set("shock", e.target.value === "" ? "" : Number(e.target.value))} /></span>}>
        <table><thead><tr><th>방법</th><th>손익</th><th>재평가 대비 오차</th><th className="l">설명</th></tr></thead><tbody>
          <tr><td>Delta만 사용</td><td><Signed v={sc.delta_only} /></td><td><Signed v={sc.error_delta_only} /></td><td className="wrap">Delta × 가격 변화. 1차 근사</td></tr>
          <tr><td>Delta + Gamma</td><td><Signed v={sc.delta_gamma} /></td><td><Signed v={sc.error_delta_gamma} /></td><td className="wrap">½ × Gamma × 가격 변화² 추가. 2차 근사</td></tr>
          <tr><td>재평가 (Full Reprice)</td><td><Signed v={sc.full_reprice} /></td><td>기준</td><td className="wrap">바뀐 현물가로 모형을 다시 계산</td></tr>
        </tbody></table>
        <p className="note">충격이 클수록 Delta만 쓴 근사의 오차가 커짐. 가격이 움직이면 Delta 자체가 변하기 때문임.</p>
      </Card>}
      {r?.curves && <div className="grid g2" style={{ marginTop: 12 }}>
        <Card title="현물가에 따른 포지션 가치와 만기 지급액">
          <ResponsiveContainer width="100%" height={220}><LineChart data={r.curves.by_spot}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="spot" {...axis} tickFormatter={(v) => fmt(v, 0)} type="number" domain={["dataMin", "dataMax"]} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "현물가 " + fmt(v)} /><Legend />
            <ReferenceLine x={f.spot} stroke="var(--mut)" strokeDasharray="3 3" />
            <Line name="현재 가치" dataKey="price" stroke="var(--chart1)" dot={false} isAnimationActive={false} />
            <Line name="만기 지급액" dataKey="payoff" stroke="var(--chart2)" dot={false} strokeDasharray="4 3" isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
        <Card title="현물가에 따른 Delta와 Gamma">
          <ResponsiveContainer width="100%" height={220}><LineChart data={r.curves.by_spot}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="spot" {...axis} tickFormatter={(v) => fmt(v, 0)} type="number" domain={["dataMin", "dataMax"]} />
            <YAxis yAxisId="l" {...axis} width={45} /><YAxis yAxisId="r" orientation="right" {...axis} width={45} />
            <Tooltip {...chartTip} formatter={(v: any) => fmt(v, 3)} labelFormatter={(v) => "현물가 " + fmt(v)} /><Legend />
            <ReferenceLine yAxisId="l" x={f.spot} stroke="var(--mut)" strokeDasharray="3 3" />
            <Line yAxisId="l" name="Delta (주)" dataKey="delta" stroke="var(--chart1)" dot={false} isAnimationActive={false} />
            <Line yAxisId="r" name="Gamma" dataKey="gamma" stroke="var(--chart3)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
        <Card title="잔존만기에 따른 Theta (1일당)">
          <ResponsiveContainer width="100%" height={200}><LineChart data={r.curves.by_time}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="days_to_expiry" {...axis} reversed /><YAxis {...axis} width={50} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "잔존 " + v + "일"} />
            <Line name="Theta" dataKey="theta_per_day" stroke="var(--chart4)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
          <p className="note">현물가가 행사가 부근이면 만기가 가까울수록 하루 감소 폭이 커지고 행사가에서 멀면 줄어듦.</p>
        </Card>
        <Card title="변동성에 따른 포지션 가치">
          <ResponsiveContainer width="100%" height={200}><LineChart data={r.curves.by_vol}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="vol" {...axis} tickFormatter={(v) => fmt(v * 100, 0) + "%"} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v: any) => "변동성 " + fmt(v * 100, 0) + "%"} />
            <Line name="가치" dataKey="price" stroke="var(--chart2)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
      </div>}
      {r && <ul className="note">{r.warnings.map((w: string, k: number) => <li key={k}>{w}</li>)}<li>평가 기록 번호 {r.valuation_id} · 모형 {r.model_version}</li></ul>}
    </>
  );
}
