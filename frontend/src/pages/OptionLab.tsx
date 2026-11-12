import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, Field, fmt, Kpi, Loading, Signed, usd, useAsync, useDebounced } from "../ui";

const GREEKS: [string, string][] = [["delta_shares", "Delta"], ["gamma_per_usd", "Gamma"], ["vega_per_1volpt_usd", "Vega"], ["theta_per_calendar_day_usd", "Theta"], ["rho_per_100bp_usd", "Rho"]];

export default function OptionLab({ snap }: Ctx) {
  const i = snap.inputs;
  const init = (u: string) => ({ underlying: u, option_type: u === "SPY" ? "CALL" : "PUT", side: u === "SPY" ? -1 : 1, contracts: 1, spot: i.spots[u].value, strike: i.spots[u].value,
    days: u === "SPY" ? 90 : 180, r: +(i.curve[0].value * 100).toFixed(2), q: +(i.divs[u].value * 100).toFixed(2), vol: +(i.vols[u].value * 100).toFixed(2), shock: 5 });
  const [f, setF] = useState<any>(init("SPY"));
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
      <h1>② 옵션 가격결정</h1>
      <div className="grid g2">
        <Card title="계약 조건 · 시장 입력 (장부 미반영)">
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
            <button className="b sec" onClick={() => { setF(init(f.underlying)); setEdited(false); }}>초기화</button>
          </div>
        </Card>
        <div>
          <Err e={res.error} />{res.loading && <Loading />}
          {r && <>
            <div className="grid g3" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
              <Kpi label="이론가 (주당)" value={usd(r.model_price_per_share_usd, 4)} />
              <Kpi label="이론가 (계약당)" value={usd(r.model_price_per_contract_usd)} />
              <Kpi label="포지션 평가금액" value={<Signed v={r.signed_position_mtm_usd} />} />
            </div>
            <Card title="포지션 Greeks">
              <table><thead><tr><th>지표</th><th>값</th><th className="l">기준</th></tr></thead><tbody>
                {GREEKS.map(([k, n]) => <tr key={k}><td>{n}</td>
                  <td><Signed v={g[k]} d={k === "gamma_per_usd" ? 4 : 2} unit={k === "delta_shares" ? "주" : k === "gamma_per_usd" ? "" : "$"} /></td><td className="wrap">{r.units[k]}</td></tr>)}
              </tbody></table>
            </Card>
          </>}
        </div>
      </div>
      {r && sc && <Card title="현물가 충격 손익: Greeks 근사와 재평가" right={<span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><span className="mut">현물가 충격 %</span><input className="q" type="number" value={f.shock} onChange={(e) => set("shock", e.target.value === "" ? "" : Number(e.target.value))} /></span>}>
        <table><thead><tr><th>방법</th><th>손익</th><th>오차</th><th className="l">산식</th></tr></thead><tbody>
          <tr><td>Delta 근사</td><td><Signed v={sc.delta_only} /></td><td><Signed v={sc.error_delta_only} /></td><td className="wrap">Delta × ΔS</td></tr>
          <tr><td>Delta + Gamma 근사</td><td><Signed v={sc.delta_gamma} /></td><td><Signed v={sc.error_delta_gamma} /></td><td className="wrap">Delta × ΔS + ½ × Gamma × ΔS²</td></tr>
          <tr><td>재평가 (Full Repricing)</td><td><Signed v={sc.full_reprice} /></td><td>기준</td><td className="wrap">충격 후 현물가로 모형 재계산</td></tr>
        </tbody></table>
      </Card>}
      {r?.curves && <div className="grid g2" style={{ marginTop: 12 }}>
        <Card title="현물가별 포지션 가치 · 만기 payoff">
          <ResponsiveContainer width="100%" height={220}><LineChart data={r.curves.by_spot}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="spot" {...axis} tickFormatter={(v) => fmt(v, 0)} type="number" domain={["dataMin", "dataMax"]} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "현물가 " + fmt(v)} /><Legend />
            <ReferenceLine x={f.spot} stroke="var(--mut)" strokeDasharray="3 3" />
            <Line name="현재 가치" dataKey="price" stroke="var(--chart1)" dot={false} isAnimationActive={false} />
            <Line name="만기 payoff (프리미엄 제외)" dataKey="payoff" stroke="var(--chart2)" dot={false} strokeDasharray="4 3" isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
        <Card title="현물가별 Delta · Gamma">
          <ResponsiveContainer width="100%" height={220}><LineChart data={r.curves.by_spot}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="spot" {...axis} tickFormatter={(v) => fmt(v, 0)} type="number" domain={["dataMin", "dataMax"]} />
            <YAxis yAxisId="l" {...axis} width={45} /><YAxis yAxisId="r" orientation="right" {...axis} width={45} />
            <Tooltip {...chartTip} formatter={(v: any) => fmt(v, 3)} labelFormatter={(v) => "현물가 " + fmt(v)} /><Legend />
            <ReferenceLine yAxisId="l" x={f.spot} stroke="var(--mut)" strokeDasharray="3 3" />
            <Line yAxisId="l" name="Delta (주)" dataKey="delta" stroke="var(--chart1)" dot={false} isAnimationActive={false} />
            <Line yAxisId="r" name="Gamma" dataKey="gamma" stroke="var(--chart3)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
        <Card title="잔존만기별 Theta (1일)">
          <ResponsiveContainer width="100%" height={200}><LineChart data={r.curves.by_time}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="days_to_expiry" {...axis} reversed /><YAxis {...axis} width={50} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "잔존 " + v + "일"} />
            <Line name="Theta" dataKey="theta_per_day" stroke="var(--chart4)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
        <Card title="변동성별 포지션 가치">
          <ResponsiveContainer width="100%" height={200}><LineChart data={r.curves.by_vol}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="vol" {...axis} tickFormatter={(v) => fmt(v * 100, 0) + "%"} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v: any) => "변동성 " + fmt(v * 100, 0) + "%"} />
            <Line name="가치" dataKey="price" stroke="var(--chart2)" dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>
        </Card>
      </div>}
    </>
  );
}
