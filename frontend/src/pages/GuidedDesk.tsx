import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, send } from "../api";
import type { Deal } from "../App";
import DealSummary from "../components/DealSummary";
import { axis, Card, chartTip, Err, fmt, Kpi, Loading, pct, Signed, usd, useAsync, useDebounced } from "../ui";

export const STEPS = ["① 가격결정", "② Greeks", "③ 델타 헤지", "④ 스트레스 테스트", "⑤ 구조화"];
const TITLES = ["① 가격결정 (Pricing)", "② 위험 민감도 (Greeks)", "③ 델타 헤지 (Delta Hedging)", "④ 스트레스 테스트 (Stress Test)", "⑤ 구조화 (Structuring)"];
const BOOK = "DEAL";
const SCENARIOS = [{ id: "up5", name: "SPY +5%", spot_pct: { SPY: 5 } }, { id: "dn5", name: "SPY −5%", spot_pct: { SPY: -5 } }, { id: "vol5", name: "변동성 +5%p", vol_pts: 5 }];
const sgn = (v: number, d = 2) => (v < 0 ? "−" : "+") + fmt(Math.abs(v), d);
const sUsd = (v: number, d = 2) => (v < 0 ? "−$" : "+$") + fmt(Math.abs(v), d);

type P = { deal: Deal; ver: number; bump: () => void; step: number; setStep: (n: number) => void; start: (s: "base" | "market") => void; openAdvanced: (page: string) => void };

export default function GuidedDesk({ deal, ver, bump, step, setStep, start, openAdvanced }: P) {
  const sid = deal.snap.snapshot_id;
  const st = useAsync();
  useEffect(() => {
    const body = { snapshot_id: sid, book: BOOK };
    st.run(() => Promise.all([get(`/book?book=${BOOK}&snapshot_id=${sid}`), send("/risk/portfolio", body), send("/hedge/delta", body)])
      .then(([book, risk, hedge]) => ({ book, risk, hedge })));
  }, [sid, ver]);

  const d = st.data;
  if (st.error) return <Err e={st.error} />;
  if (!d) return <Loading text="재평가 중" />;
  const opt = d.book.positions.find((p: any) => p.instrument_type === "EUROPEAN_OPTION");
  const row = d.risk.rows.find((r: any) => r.position_id === opt.id);
  const shares = d.book.positions.find((p: any) => p.instrument_type === "SPOT")?.signed_quantity ?? 0;
  const days = Math.round((Date.parse(opt.spec.expiry) - Date.parse(deal.snap.as_of)) / 86400000);
  const S = deal.snap.inputs.spots.SPY.value;
  // 장부 평가와 동일한 입력으로 단일 계약 평가 API를 호출한다.
  const req = { underlying: "SPY", option_type: opt.spec.option_type, spot: S, strike: opt.spec.strike, valuation_date: deal.snap.as_of, expiry: opt.spec.expiry,
    risk_free_rate: row.detail.r, dividend_yield: row.detail.q, volatility: row.detail.sigma, multiplier: opt.spec.multiplier, signed_quantity: opt.signed_quantity, input_mode: deal.snap.mode };
  const x = { deal, sid, ver, bump, opt, row, shares, S, req, risk: d.risk, plan: d.hedge.plan.SPY, trades: d.book.hedge_trades, openAdvanced };
  return (
    <>
      <h1>{TITLES[step]}</h1>
      <DealSummary deal={deal} opt={opt} det={row.detail} shares={shares} days={days} start={start} />
      {step === 0 && <Pricing {...x} />}
      {step === 1 && <Greeks {...x} />}
      {step === 2 && <HedgeStep {...x} />}
      {step === 3 && <StressStep {...x} />}
      {step === 4 && <Note {...x} />}
      <div className="stepnav">
        {step > 0 ? <button className="b sec" onClick={() => setStep(step - 1)}>이전: {STEPS[step - 1].slice(2)}</button> : <span />}
        {step < STEPS.length - 1 && <button className="b" onClick={() => setStep(step + 1)}>다음: {STEPS[step + 1].slice(2)}</button>}
      </div>
    </>
  );
}

function Pricing({ opt, row, S, req, sid, ver }: any) {
  const cv = useAsync();
  useEffect(() => { cv.run(() => send("/pricing/european", { ...req, curves: true })); }, [sid, ver]);
  const n = Math.abs(opt.signed_quantity), mult = opt.spec.multiplier;
  const premium = opt.spec.trade_price_per_share * mult * n;
  const data = cv.data?.curves.by_spot.map((p: any) => ({ spot: p.spot, payoff: p.payoff, pnl: p.payoff + premium })) ?? [];
  return (
    <>
      <p className="lead">고객에게 SPY 콜옵션 <b>{fmt(n, 0)}계약</b>을 매도함. 만기 SPY 가격이 행사가 {usd(opt.spec.strike)}를 초과하면 초과분 × {fmt(mult * n, 0)}주를 지급함. BSM 이론가는 계약당 <b>{usd(row.unit_price)}</b>.</p>
      <div className="grid g3">
        <Kpi label="계약당 이론가 (BSM)" value={usd(row.unit_price)} sub={`주당 ${usd(row.detail.per_share, 4)} × ${fmt(mult, 0)}주`} />
        <Kpi label="수취 프리미엄 (거래 시점)" value={<Signed v={premium} />} sub={`${opt.spec.trade_date} · 이론가 체결 가정`} />
        <Kpi label="포지션 평가금액 (MTM)" value={<Signed v={row.mtm} />} sub="매도 포지션: 지급 의무의 현재가치" />
      </div>
      <Card title="만기 SPY 가격별 매도자 손익 (USD)">
        <Err e={cv.error} />{cv.loading && <Loading />}
        {cv.data && <ResponsiveContainer width="100%" height={280}><LineChart data={data}><CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey="spot" type="number" domain={["dataMin", "dataMax"]} {...axis} tickFormatter={(v) => fmt(v, 0)} /><YAxis {...axis} width={60} tickFormatter={(v) => fmt(v, 0)} />
          <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "만기 SPY " + usd(v)} /><Legend />
          <ReferenceLine y={0} stroke="var(--mut)" /><ReferenceLine x={opt.spec.strike} stroke="var(--line)" label={{ value: "행사가", fill: "var(--mut)", fontSize: 10, position: "insideTopLeft" }} />
          <Line name="만기 지급액 (프리미엄 제외)" dataKey="payoff" stroke="var(--chart2)" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Line name="프리미엄 포함 만기 손익" dataKey="pnl" stroke="var(--chart1)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart></ResponsiveContainer>}
      </Card>
      <details><summary>평가 입력 · 산식</summary>
        <table><tbody>
          <tr><td>모형</td><td>Black-Scholes-Merton (유럽형, 연속 배당)</td></tr>
          <tr><td>S / K</td><td>{usd(S)} / {usd(opt.spec.strike)}</td></tr>
          <tr><td>T</td><td>{fmt(row.detail.T, 4)}년 (Act/365)</td></tr>
          <tr><td>r / q / σ</td><td>{pct(row.detail.r)} / {pct(row.detail.q)} / {pct(row.detail.sigma)}</td></tr>
          {cv.data && <tr><td>d1 / d2</td><td>{fmt(cv.data.d1, 4)} / {fmt(cv.data.d2, 4)}</td></tr>}
          <tr><td>이론가의 성격</td><td>모형 추정값. 거래소 호가 또는 고객 제시가격과 상이</td></tr>
        </tbody></table>
      </details>
    </>
  );
}

function Greeks({ row, S, req, sid, ver }: any) {
  const [shock, setShock] = useState<{ name: string; pct: number }>({ name: "SPY +$1", pct: 100 / S });
  const res = useAsync();
  useEffect(() => { res.run(() => send("/pricing/european", { ...req, spot_shock_pct: shock.pct, curves: true })); }, [sid, ver, shock.pct]);
  const dl = row.delta.SPY, r = res.data, sc = r?.shock_compare, g = r?.greeks_position;
  const rows: [string, string, number, number][] = g ? [["Delta", "delta_shares", g.delta_shares, 2], ["Gamma", "gamma_per_usd", g.gamma_per_usd, 4], ["Vega", "vega_per_1volpt_usd", g.vega_per_1volpt_usd, 2],
    ["Theta", "theta_per_calendar_day_usd", g.theta_per_calendar_day_usd, 2], ["Rho", "rho_per_100bp_usd", g.rho_per_100bp_usd, 2]] : [];
  return (
    <>
      <p className="lead">포지션 Delta <b>{sgn(dl)}주</b>. SPY가 $1 상승하면 포지션 평가금액이 약 <b>{usd(Math.abs(dl))}</b> {dl < 0 ? "감소" : "증가"}함(1차 근사). 주식 {fmt(Math.abs(dl), 1)}주 {dl < 0 ? "매도" : "매수"}와 동일한 가격 노출.</p>
      <div className="grid g3">
        <Kpi label="Delta (주식 환산)" value={<Signed v={dl} unit="주" />} sub={`주당 ${fmt(row.detail.delta_per_share, 4)} × 100주 × 매도`} />
        <Kpi label="Gamma" value={<Signed v={row.gamma.SPY} d={4} unit="" />} sub="SPY $1 상승 시 Delta 변화" />
        <Kpi label="Vega" value={<Signed v={row.vega.SPY} />} sub="변동성 +1%p 시 평가금액 변화" />
      </div>
      <div className="grid g2">
        <Card title="현물가 충격: Delta 근사와 재평가" right={<span className="seg">{[["SPY +$1", 100 / S], ["SPY −$1", -100 / S], ["SPY +5%", 5], ["SPY −5%", -5]].map(([n, p]: any) =>
          <button key={n} className={shock.name === n ? "on" : ""} onClick={() => setShock({ name: n, pct: p })}>{n}</button>)}</span>}>
          <Err e={res.error} />{res.loading && <Loading text="재평가 중" />}
          {sc && <table><thead><tr><th>산출 방법</th><th>평가손익</th><th>재평가 대비 오차</th></tr></thead><tbody>
            <tr><td>Delta 근사</td><td><Signed v={sc.delta_only} /></td><td><Signed v={sc.error_delta_only} /></td></tr>
            <tr><td>Delta + Gamma 근사</td><td><Signed v={sc.delta_gamma} /></td><td><Signed v={sc.error_delta_gamma} /></td></tr>
            <tr><td>재평가 (Full Repricing)</td><td><Signed v={sc.full_reprice} /></td><td>—</td></tr>
          </tbody></table>}
        </Card>
        <Card title="SPY 현물가별 포지션 평가금액 (USD)">
          {r && <ResponsiveContainer width="100%" height={200}><LineChart data={r.curves.by_spot}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="spot" type="number" domain={["dataMin", "dataMax"]} {...axis} tickFormatter={(v) => fmt(v, 0)} /><YAxis {...axis} width={60} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v) => "SPY " + usd(v)} />
            <ReferenceLine x={S} stroke="var(--mut)" strokeDasharray="4 3" label={{ value: "현재", fill: "var(--mut)", fontSize: 10, position: "insideTopLeft" }} />
            <Line name="평가금액" dataKey="price" stroke="var(--chart1)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart></ResponsiveContainer>}
        </Card>
      </div>
      <details><summary>전체 Greeks (포지션 기준)</summary>
        {g && <table><thead><tr><th>지표</th><th>값</th><th className="l">기준</th></tr></thead><tbody>
          {rows.map(([n, k, v, dd]) => <tr key={k}><td>{n}</td><td><Signed v={v} d={dd} unit={k === "delta_shares" ? "주" : k === "gamma_per_usd" ? "" : "$"} /></td><td className="l">{r.units[k]}</td></tr>)}
        </tbody></table>}
      </details>
    </>
  );
}

function HedgeStep({ sid, bump, row, shares, plan, trades, risk, S }: any) {
  const [err, setErr] = useState<any>(null);
  const apply = () => send("/hedge/delta", { snapshot_id: sid, book: BOOK, apply: true }).then(bump).catch(setErr);
  const net = plan.net_delta_before, none = plan.trade_shares === 0;
  // 헤지 전 = 옵션 단독, 헤지 후 = 제안 거래까지 반영한 장부. 동일한 Delta + Gamma 근사식을 적용한다.
  const ds = 0.01 * S, od = row.delta.SPY, og = row.gamma.SPY;
  const bars = [{ name: "SPY +1%", "헤지 전": od * ds + 0.5 * og * ds * ds, "헤지 후": plan.pnl_1pct_up_after }, { name: "SPY −1%", "헤지 전": -od * ds + 0.5 * og * ds * ds, "헤지 후": plan.pnl_1pct_dn_after }];
  return (
    <>
      <p className="lead">{none
        ? <>SPY 현물 <b>{fmt(shares, 0)}주</b> 보유로 순 Delta <b>{sgn(net)}주</b>. 추가 거래 없음. Gamma·Vega 위험은 잔존함.</>
        : <>옵션 Delta {sgn(row.delta.SPY)}주를 상쇄하기 위해 SPY <b>{fmt(Math.abs(plan.trade_shares), 0)}주 {plan.side}</b>. 거래 후 순 Delta <b>{sgn(plan.net_delta_after)}주</b>. 가격의 1차 민감도가 축소되며 Gamma·Vega 위험은 잔존함.</>}</p>
      <Err e={err} />
      <div className="grid g4">
        <Kpi label="현물 보유" value={`${fmt(shares, 0)}주`} />
        <Kpi label="순 Delta" value={<Signed v={net} unit="주" />} sub={`옵션 ${sgn(row.delta.SPY)} + 현물 ${sgn(shares, 0)}`} />
        <Kpi label="제안 거래" value={none ? "거래 없음" : `${plan.side} ${fmt(Math.abs(plan.trade_shares), 0)}주`} sub={none ? undefined : `거래 비용 ${usd(plan.estimated_cost)} (1bp)`} />
        <Kpi label="거래 후 순 Delta" value={<Signed v={plan.net_delta_after} unit="주" />} />
      </div>
      <div className="row" style={{ margin: "0 0 16px" }}><button className="b" onClick={apply} disabled={none}>가상 헤지 적용</button></div>
      <div className="grid g2">
        <Card title="SPY ±1% 평가손익 (Delta + Gamma 근사, USD)">
          <ResponsiveContainer width="100%" height={200}><BarChart data={bars}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="name" {...axis} /><YAxis {...axis} width={50} tickFormatter={(v) => fmt(v, 0)} /><ReferenceLine y={0} stroke="var(--mut)" />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} cursor={{ fill: "var(--panel2)" }} /><Legend />
            <Bar dataKey="헤지 전" fill="var(--chart2)" isAnimationActive={false} /><Bar dataKey="헤지 후" fill="var(--chart1)" isAnimationActive={false} />
          </BarChart></ResponsiveContainer>
        </Card>
        <Card title="잔여 위험 · 가상 거래 내역">
          <table><tbody>
            <tr><td>Gamma</td><td><Signed v={risk.totals.gamma.SPY} d={4} unit="" /></td></tr>
            <tr><td>Vega (변동성 +1%p)</td><td><Signed v={risk.totals.vega.SPY} /></td></tr>
            {trades.map((t: any) => <tr key={t.id}><td>{new Date(t.created_at).toLocaleString("ko-KR")} · SPY {sgn(t.shares, 0)}주 @ {usd(t.price)}</td><td>비용 {usd(t.cost)}</td></tr>)}
          </tbody></table>
        </Card>
      </div>
    </>
  );
}

function StressStep({ sid, ver, row, shares, risk }: any) {
  const [sel, setSel] = useState(0);
  const st = useAsync();
  useEffect(() => { st.run(() => send("/risk/stress", { snapshot_id: sid, book: BOOK, scenarios: SCENARIOS })); }, [sid, ver]);
  if (st.error) return <Err e={st.error} />;
  if (!st.data) return <Loading text="시나리오 재평가 중" />;
  const oi = st.data.positions.findIndex((p: any) => p.instrument_type === "EUROPEAN_OPTION");
  const si = st.data.positions.findIndex((p: any) => p.instrument_type === "SPOT");
  const sc = st.data.scenarios[sel], o = sc.by_position[oi], s = sc.by_position[si];
  const bars = st.data.scenarios.map((z: any) => ({ name: z.name, "헤지 전": z.by_position[oi], "현재 장부": z.pnl_full_reprice }));
  return (
    <>
      <p className="lead"><b>{sc.name}</b> 충격 시 평가손익은 헤지 전 <b>{sUsd(o)}</b>, 현재 장부(현물 {fmt(shares, 0)}주) <b>{sUsd(sc.pnl_full_reprice)}</b>.{shares === 0 ? " 현물 헤지 미적용 상태." : " Delta 중립 이후에도 Gamma·Vega에 의한 손익이 잔존함."}</p>
      <div className="row" style={{ margin: "0 0 14px" }}><span className="seg">{SCENARIOS.map((z, k) => <button key={z.id} className={sel === k ? "on" : ""} onClick={() => setSel(k)}>{z.name}</button>)}</span></div>
      <div className="grid g2">
        <Card title={`${sc.name}: 재평가 (Full Repricing)`}>
          <table><thead><tr><th>항목</th><th>헤지 전</th><th>현재 장부 (현물 {fmt(shares, 0)}주)</th></tr></thead><tbody>
            <tr><td>옵션 평가금액 변화</td><td><Signed v={o} /></td><td><Signed v={o} /></td></tr>
            <tr><td>현물 평가금액 변화</td><td><Signed v={0} /></td><td><Signed v={s} /></td></tr>
            <tr style={{ fontWeight: 700 }}><td>합산 평가손익</td><td><Signed v={o} /></td><td><Signed v={sc.pnl_full_reprice} /></td></tr>
            <tr><td>충격 전 순 Delta</td><td><Signed v={row.delta.SPY} unit="주" /></td><td><Signed v={risk.totals.delta.SPY} unit="주" /></td></tr>
          </tbody></table>
        </Card>
        <Card title="시나리오별 합산 평가손익 (USD)">
          <ResponsiveContainer width="100%" height={200}><BarChart data={bars}><CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="name" {...axis} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} /><ReferenceLine y={0} stroke="var(--mut)" />
            <Tooltip {...chartTip} formatter={(v: any) => usd(v)} cursor={{ fill: "var(--panel2)" }} /><Legend />
            <Bar dataKey="헤지 전" fill="var(--chart2)" isAnimationActive={false} /><Bar dataKey="현재 장부" fill="var(--chart1)" isAnimationActive={false} />
          </BarChart></ResponsiveContainer>
        </Card>
      </div>
      <details><summary>현재 장부의 Greeks 근사와 재평가 비교</summary>
        <table><thead><tr><th>시나리오</th><th>Delta 근사</th><th>Delta + Gamma 근사</th><th>Delta + Gamma + Vega 근사</th><th>재평가</th></tr></thead><tbody>
          {st.data.scenarios.map((z: any) => <tr key={z.id}><td>{z.name}</td><td><Signed v={z.approx.delta_only} /></td><td><Signed v={z.approx.delta_gamma} /></td><td><Signed v={z.approx.all_greeks} /></td><td><Signed v={z.pnl_full_reprice} /></td></tr>)}
        </tbody></table>
        <p className="note">Delta는 현재 가격 부근의 1차 근사이며 충격이 클수록 재평가와의 차이가 확대됨. 평가손익은 충격 직후 평가금액 변화이며 프리미엄·거래 비용을 포함한 확정 손익과 상이함.</p>
      </details>
    </>
  );
}

function Note({ deal, row, S, sid, openAdvanced }: any) {
  const [a, setA] = useState(50);
  const da = useDebounced(a, 150);
  const res = useAsync(), mc = useAsync();
  const body = { notional: 1000, participation: da / 100, reference_level: S, spot: S, tenor_years: 1, risk_free_rate: row.detail.r, dividend_yield: row.detail.q, volatility: row.detail.sigma, issue_price: 1000 };
  useEffect(() => { mc.setData(null); if (da !== "" as any) res.run(() => send("/simple-structuring/price", body)); }, [sid, da]);
  const r = res.data, g = r?.greeks;
  const curve = r?.payoff_curve.map((p: any) => ({ x: (p.ratio - 1) * 100, payoff: p.payoff })) ?? [];
  return (
    <>
      <p className="lead">만기 SPY가 기준가 {usd(S)} 이하이면 원금 $1,000, 초과이면 상승률의 <b>{fmt(da, 0)}%</b>를 가산해 지급하는 원금지급형 주가연계 채권(1년).{r && <> 이론가 <b>{usd(r.price)}</b> = 할인채 {usd(r.bond_value)} + 콜옵션 {usd(r.option_value)}.</>}</p>
      <div className="row" style={{ margin: "0 0 14px" }}>
        <label style={{ width: 300 }}>상승 참여율 {fmt(a, 0)}%<input type="range" min={0} max={150} step={5} value={a} onChange={(e) => setA(Number(e.target.value))} style={{ padding: 0 }} /></label>
        <button className="b sec" onClick={() => openAdvanced("struct")}>조기상환 · 낙인 구조 (고급)</button>
      </div>
      <Err e={res.error} />{res.loading && <Loading text="재평가 중" />}
      {r && <>
        <div className="grid g4">
          <Kpi label="이론가 (투자자, 1개)" value={usd(r.price)} sub={<>발행가 $1,000 − 이론가 <Signed v={r.issue_minus_model} /></>} />
          <Kpi label="할인채 (원금 지급분)" value={usd(r.bond_value)} sub="$1,000 × exp(−rT)" />
          <Kpi label="콜옵션 (상승 참여분)" value={usd(r.option_value)} sub={`${fmt(r.call_units, 2)}주 × ${usd(r.call_per_share, 4)}`} />
          <Kpi label="발행가 일치 참여율" value={r.par_participation == null ? "N/A" : pct(r.par_participation, 1)} sub="신용위험 · 비용 미반영" />
        </div>
        <div className="grid g2">
          <Card title="만기 SPY 수익률별 지급액 (투자자, USD)">
            <ResponsiveContainer width="100%" height={220}><LineChart data={curve}><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="x" type="number" domain={[-40, 40]} {...axis} tickFormatter={(v) => (v > 0 ? "+" : "") + fmt(v, 0) + "%"} /><YAxis {...axis} width={55} domain={[900, "auto"]} tickFormatter={(v) => fmt(v, 0)} />
              <Tooltip {...chartTip} formatter={(v: any) => usd(v)} labelFormatter={(v: any) => "SPY " + (v > 0 ? "+" : "") + fmt(v, 0) + "%"} />
              <ReferenceLine x={0} stroke="var(--line)" /><Line name="만기 지급액" dataKey="payoff" stroke="var(--chart1)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart></ResponsiveContainer>
            <table><thead><tr><th>만기 SPY</th>{r.examples.map((e: any) => <th key={e.ratio}>{e.ratio === 1 ? "0%" : (e.ratio > 1 ? "+" : "−") + fmt(Math.abs(e.ratio - 1) * 100, 0) + "%"}</th>)}</tr></thead>
              <tbody><tr><td>지급액</td>{r.examples.map((e: any) => <td key={e.ratio}>{usd(e.payoff)}</td>)}</tr></tbody></table>
          </Card>
          <Card title="Greeks (투자자, 1개)">
            <table><tbody>
              <tr><td>Delta (주식 환산)</td><td><Signed v={g.delta_shares} unit="주" /></td></tr>
              <tr><td>Gamma</td><td><Signed v={g.gamma_per_usd} d={4} unit="" /></td></tr>
              <tr><td>Vega (변동성 +1%p)</td><td><Signed v={g.vega_per_1volpt_usd} /></td></tr>
              <tr><td>Theta (1일)</td><td><Signed v={g.theta_per_calendar_day_usd} /></td></tr>
              <tr><td>Rho (금리 +100bp)</td><td><Signed v={g.rho_per_100bp_usd} /></td></tr>
            </tbody></table>
          </Card>
        </div>
        <details><summary>산식 · Monte Carlo 대조</summary>
          <p className="note" style={{ marginTop: 6 }}>V₀ = N·exp(−rT) + (α·N/S₀)·C(S, K=S₀, T, r, q, σ). 발행자 포지션은 반대 부호.</p>
          <div className="row"><button className="b sec" onClick={() => mc.run(() => send("/simple-structuring/price", { ...body, mc_check: true }))} disabled={mc.loading}>Monte Carlo 대조 (200,000 경로)</button></div>
          <Err e={mc.error} />{mc.loading && <Loading />}
          {mc.data && <table><thead><tr><th>분석식</th><th>Monte Carlo</th><th>표준오차</th><th>차이</th></tr></thead><tbody>
            <tr><td>{usd(mc.data.price, 4)}</td><td>{usd(mc.data.mc.price, 4)}</td><td>{fmt(mc.data.mc.std_error, 4)}</td><td><Signed v={mc.data.mc.diff} d={4} /></td></tr></tbody></table>}
        </details>
      </>}
    </>
  );
}
