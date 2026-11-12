import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, CAT_KR, chartTip, Err, Field, fmt, Kpi, Loading, pct, Signed, usd, useAsync } from "../ui";

export default function Structuring({ snap, nPaths, seed }: Ctx) {
  const i = snap.inputs;
  const init = () => ({ b1: 95, b2: 90, b3: 85, mb: 80, ki: 60, coupon: 10, qty: -10,
    s1: i.spots.SPY.value, s2: i.spots.QQQ.value, v1: +(i.vols.SPY.value * 100).toFixed(2), v2: +(i.vols.QQQ.value * 100).toFixed(2),
    q1: +(i.divs.SPY.value * 100).toFixed(2), q2: +(i.divs.QQQ.value * 100).toFixed(2), r: +(i.curve[i.curve.length - 1].value * 100).toFixed(2), rho: +i.corr.value.toFixed(3) });
  const [f, setF] = useState<any>(init());
  const [edited, setEdited] = useState(false);
  const [tab, setTab] = useState("design");
  const ex = useAsync(), pr = useAsync(), cv = useAsync();
  const set = (k: string, v: any) => { setF({ ...f, [k]: v }); setEdited(true); };
  useEffect(() => { setF(init()); setEdited(false); pr.setData(null); cv.setData(null); }, [snap.snapshot_id]);

  const spec = { notional: 1000, tenor_years: 2, autocall_times: [0.5, 1.0, 1.5], autocall_barriers: [f.b1 / 100, f.b2 / 100, f.b3 / 100], maturity_barrier: f.mb / 100, ki_barrier: f.ki / 100, coupon_rate: f.coupon / 100 };
  const market = { spot_1: f.s1, spot_2: f.s2, vol_1: f.v1 / 100, vol_2: f.v2 / 100, div_1: f.q1 / 100, div_2: f.q2 / 100, rate: f.r / 100, corr: f.rho };
  useEffect(() => { ex.run(() => send("/structuring/payoff", { spec })); }, [JSON.stringify(spec)]);
  const price = () => { setTab("price"); cv.setData(null); pr.run(() => send("/structuring/price", { spec, market, issue_date: snap.as_of, n_paths: nPaths, seed, signed_quantity: f.qty, input_mode: edited ? "MANUAL SCENARIO" : snap.mode })); };
  const p = pr.data, c = f.coupon / 100;
  const dist = p ? Object.entries(p.distribution.category_fraction).map(([k, v]: any) => ({ name: CAT_KR[k] || k, pct: v * 100 })) : [];
  const paths = p?.sample_paths ? p.sample_paths.t.map((t: number, k: number) => { const o: any = { t }; p.sample_paths.ratio1.slice(0, 25).forEach((r1: number[], j: number) => { o["p" + j] = Math.min(r1[k], p.sample_paths.ratio2[j][k]) * 100; }); return o; }) : [];

  return (
    <>
      <h1>③ 구조화상품 설계 · 평가</h1>
      <div className="grid g2">
        <Card title="계약 조건 (Term Sheet)">
          <div className="form">
            <Field label="6개월 상환 배리어 %" value={f.b1} onChange={(v) => set("b1", v)} />
            <Field label="12개월 상환 배리어 %" value={f.b2} onChange={(v) => set("b2", v)} />
            <Field label="18개월 상환 배리어 %" value={f.b3} onChange={(v) => set("b3", v)} />
            <Field label="만기 상환 배리어 %" value={f.mb} onChange={(v) => set("mb", v)} />
            <Field label="낙인 배리어 %" value={f.ki} onChange={(v) => set("ki", v)} />
            <Field label="쿠폰 (연 %)" value={f.coupon} step={0.5} onChange={(v) => set("coupon", v)} />
            <Field label="수량 (매도 -)" value={f.qty} onChange={(v) => set("qty", v)} />
          </div>
        </Card>
        <Card title="모형 입력">
          <div className="form">
            <Field label="SPY 현물가" value={f.s1} onChange={(v) => set("s1", v)} /><Field label="QQQ 현물가" value={f.s2} onChange={(v) => set("s2", v)} />
            <Field label="SPY 변동성 %" value={f.v1} onChange={(v) => set("v1", v)} /><Field label="QQQ 변동성 %" value={f.v2} onChange={(v) => set("v2", v)} />
            <Field label="SPY 배당수익률 %" value={f.q1} onChange={(v) => set("q1", v)} /><Field label="QQQ 배당수익률 %" value={f.q2} onChange={(v) => set("q2", v)} />
            <Field label="금리 %" value={f.r} step={0.1} onChange={(v) => set("r", v)} /><Field label="상관계수" value={f.rho} step={0.05} onChange={(v) => set("rho", v)} />
          </div>
          <div className="row"><button className="b" onClick={price} disabled={pr.loading}>Monte Carlo 평가 ({nPaths.toLocaleString()} 경로)</button>
            <button className="b sec" onClick={() => { setF(init()); setEdited(false); }}>초기화</button></div>
        </Card>
      </div>
      <div className="row" style={{ margin: "0 0 12px" }}>
        <button className={"b " + (tab === "design" ? "" : "sec")} onClick={() => setTab("design")}>A. 손익구조</button>
        <button className={"b " + (tab === "price" ? "" : "sec")} onClick={() => setTab("price")}>B. 평가 · 위험</button>
      </div>
      {tab === "design" && <>
        <div className="grid g2">
          <Card title="상환 조건 (W = 기준가 대비 비율의 최솟값)">
            <div className="flow">
              {[["6개월", f.b1, 0.5], ["12개월", f.b2, 1.0], ["18개월", f.b3, 1.5]].map(([n, b, t]: any, k) => <div key={k}><b>{k + 1}</b>{n} 관측일 W ≥ {b}%: {usd(1000 * (1 + c * t), 0)} 조기상환</div>)}
              <div><b>4</b>만기 W ≥ {f.mb}%: {usd(1000 * (1 + c * 2), 0)} 상환</div>
              <div><b>5</b>만기 W &lt; {f.mb}%, 낙인 미발생: {usd(1000 * (1 + c * 2), 0)} 상환</div>
              <div><b>6</b>만기 W &lt; {f.mb}%, 낙인 발생(기간 중 W ≤ {f.ki}%): $1,000 × W 상환</div>
            </div>
          </Card>
          <Card title="예시 경로별 상환금액 (worst-of 경로)">
            <Err e={ex.error} />{ex.loading && <Loading />}
            {ex.data && <table><thead><tr><th>경로</th><th>상환금액</th><th>액면 대비</th><th>상환 시점</th><th className="l">낙인</th></tr></thead><tbody>
              {ex.data.examples.map((e: any) => <tr key={e.id}><td>{e.name}</td><td>{usd(e.result.amount)}</td><td><Signed v={e.result.pnl_vs_notional} /></td><td>{e.result.redeem_time}년</td><td className="l">{e.result.knocked_in ? "발생" : "미발생"}</td></tr>)}
            </tbody></table>}
            {ex.data && <ResponsiveContainer width="100%" height={200}><LineChart><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="t" type="number" domain={[0, 2]} {...axis} ticks={[0, 0.5, 1, 1.5, 2]} /><YAxis {...axis} width={40} domain={[0.4, 1.1]} tickFormatter={(v) => fmt(v * 100, 0)} />
              <Tooltip {...chartTip} formatter={(v: any) => fmt(v * 100, 1) + "%"} labelFormatter={(v) => v + "년"} />
              <ReferenceLine y={f.ki / 100} stroke="var(--neg)" strokeDasharray="4 3" label={{ value: "낙인", fill: "var(--neg)", fontSize: 10, position: "insideBottomLeft" }} />
              <ReferenceLine y={f.mb / 100} stroke="var(--mut)" strokeDasharray="4 3" />
              {ex.data.examples.map((e: any, k: number) => <Line key={e.id} data={e.result.path} name={e.name} dataKey="worst" stroke={`var(--chart${k + 1})`} dot={false} isAnimationActive={false} />)}
            </LineChart></ResponsiveContainer>}
          </Card>
        </div>
      </>}
      {tab === "price" && <>
        <Err e={pr.error} />{pr.loading && <Loading text="Monte Carlo 계산 중" />}
        {p && <>
          <div className="grid g4">
            <Kpi label="이론가 (투자자, 1개)" value={usd(p.investor.price_per_note)} sub={`표준오차 ${fmt(p.investor.std_error)}`} />
            <Kpi label="발행가 - 이론가" value={<Signed v={p.issuer_margin_per_note} />} />
            <Kpi label={`발행자 포지션 (${f.qty}개)`} value={<Signed v={p.issuer_position.mtm} />} />
            <Kpi label="만기 손실 상환 비율" value={pct(p.distribution.loss_rate, 1)} sub={`낙인 발생 ${pct(p.distribution.knock_in_rate, 1)}`} />
          </div>
          <div className="grid g2">
            <Card title="상환 유형별 경로 비율 (위험중립 측도)">
              <ResponsiveContainer width="100%" height={230}><BarChart data={dist} layout="vertical" margin={{ left: 60 }}><CartesianGrid stroke="var(--line)" horizontal={false} />
                <XAxis type="number" {...axis} tickFormatter={(v) => v + "%"} /><YAxis type="category" dataKey="name" {...axis} width={110} />
                <Tooltip {...chartTip} formatter={(v: any) => fmt(v, 1) + "%"} /><Bar dataKey="pct" name="비율" fill="var(--chart1)" isAnimationActive={false} />
              </BarChart></ResponsiveContainer>
            </Card>
            <Card title="표본 경로 25개의 W (%)">
              <ResponsiveContainer width="100%" height={230}><LineChart data={paths}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="t" type="number" domain={[0, 2]} ticks={[0, 0.5, 1, 1.5, 2]} {...axis} /><YAxis {...axis} width={40} domain={[30, 150]} allowDataOverflow />
                <ReferenceLine y={f.ki} stroke="var(--neg)" strokeDasharray="4 3" /><ReferenceLine y={f.mb} stroke="var(--mut)" strokeDasharray="4 3" /><ReferenceLine y={100} stroke="var(--line)" />
                {[0.5, 1, 1.5].map((t) => <ReferenceLine key={t} x={t} stroke="var(--line)" />)}
                {Array.from({ length: 25 }, (_, j) => <Line key={j} dataKey={"p" + j} stroke="var(--chart1)" strokeOpacity={0.35} dot={false} strokeWidth={1} isAnimationActive={false} />)}
              </LineChart></ResponsiveContainer>
            </Card>
          </div>
          <div className="grid g2">
            <Card title="Greeks · 델타 헤지 수량">
              <table><thead><tr><th>지표</th><th>SPY</th><th>QQQ</th></tr></thead><tbody>
                <tr><td>Delta (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.delta_1, 3)}</td><td>{fmt(p.greeks_investor_per_note.delta_2, 3)}</td></tr>
                <tr><td>Gamma (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.gamma_1, 4)}</td><td>{fmt(p.greeks_investor_per_note.gamma_2, 4)}</td></tr>
                <tr><td>Vega (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.vega_1_per_1volpt)}</td><td>{fmt(p.greeks_investor_per_note.vega_2_per_1volpt)}</td></tr>
                <tr><td>발행자 포지션 Delta</td><td><Signed v={p.issuer_position.delta_shares["1"]} unit="주" /></td><td><Signed v={p.issuer_position.delta_shares["2"]} unit="주" /></td></tr>
                <tr><td>델타 중립 헤지 수량 (+ 매수)</td><td><Signed v={p.issuer_position.hedge_shares["1"]} unit="주" /></td><td><Signed v={p.issuer_position.hedge_shares["2"]} unit="주" /></td></tr>
              </tbody></table>
            </Card>
            <Card title="시나리오 재평가 (투자자, 1개)">
              <table><thead><tr><th>조건</th><th>이론가</th><th>변화</th></tr></thead><tbody>
                <tr><td>SPY·QQQ −10%</td><td>{usd(p.spot_shock.down_10pct.price)}</td><td><Signed v={p.spot_shock.down_10pct.change} /></td></tr>
                <tr><td>SPY·QQQ +10%</td><td>{usd(p.spot_shock.up_10pct.price)}</td><td><Signed v={p.spot_shock.up_10pct.change} /></td></tr>
                <tr><td>상관계수 +0.10</td><td>{usd(p.corr_sensitivity.price_up)}</td><td><Signed v={p.corr_sensitivity.price_up - p.investor.price_per_note} /></td></tr>
                <tr><td>상관계수 -0.10</td><td>{usd(p.corr_sensitivity.price_down)}</td><td><Signed v={p.corr_sensitivity.price_down - p.investor.price_per_note} /></td></tr>
              </tbody></table>
              <div className="row"><button className="b sec" onClick={() => cv.run(() => send("/structuring/convergence", { spec, market, seed }))} disabled={cv.loading}>경로 수별 수렴</button></div>
              {cv.loading && <Loading />}
              {cv.data && <ResponsiveContainer width="100%" height={170}><LineChart data={cv.data.rows.map((r: any) => ({ ...r, n: String(r.n_paths), err: 1.96 * r.std_error }))}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="n" {...axis} /><YAxis {...axis} width={50} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 0)} />
                <Tooltip {...chartTip} formatter={(v: any) => fmt(v)} /><Line dataKey="price" name="이론가" stroke="var(--chart1)" isAnimationActive={false}><ErrorBar dataKey="err" stroke="var(--mut)" width={4} /></Line>
              </LineChart></ResponsiveContainer>}
            </Card>
          </div>
          <Card title="관측 일정">
            <table><thead><tr><th>회차</th><th>관측일</th><th>쿠폰 연수</th><th>할인 연수 (Act/365)</th></tr></thead><tbody>
              {p.schedule.observation_dates.map((d: string, k: number) => <tr key={k}><td>{k < 3 ? `${k + 1}차 조기상환` : "만기"}</td><td>{d}</td><td>{p.schedule.coupon_year_fractions[k]}</td><td>{fmt(p.schedule.discount_year_fractions[k], 4)}</td></tr>)}
            </tbody></table>
          </Card>
        </>}
      </>}
    </>
  );
}
