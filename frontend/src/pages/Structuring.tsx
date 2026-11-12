import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, CAT_KR, chartTip, Err, Explain, Field, fmt, Kpi, Loading, pct, Signed, usd, useAsync } from "../ui";

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
      <h1>③ 구조화 Structuring Studio</h1>
      <p className="sub">SPY·QQQ 중 더 부진한 쪽에 연동되는 조기상환형 노트(ELS 유사, 가상 계약)의 지급 규칙 설계와 Monte Carlo 평가</p>
      <Explain goal={["지급 규칙(payoff)이 계약의 핵심임을 확인", "경로에 따라 결과가 달라지는 상품을 시뮬레이션으로 평가하는 이유 이해", "투자자 가치와 발행자(매도) 포지션의 부호가 반대임을 확인"]}
        read={["이론가 = 경로별 지급액을 할인한 값의 평균. 표준오차는 시뮬레이션 잡음의 크기", "상환 분포는 위험중립 모형 아래의 경로 빈도이며 실제 발생 확률이 아님", "발행가 $1,000과 이론가의 차이는 발행자 몫이나 헤지·조달 비용은 미반영"]}
        missing={["변동성 스마일, 변동성·상관계수의 시간 변화, 가격 점프", "연속 관측 낙인(여기서는 일별 종가 관측)", "발행 후 경과한 상품의 재평가(낙인·관측 이력 필요)", "발행자 신용위험"]}
        interview="구조화는 지급 조건을 설계하는 일입니다. 이 예시는 두 ETF 중 성과가 낮은 쪽을 기준으로 조기상환과 만기 상환액이 정해집니다. 지급액이 경로에 따라 달라져 공식 하나로 계산하기 어렵기 때문에, 많은 경로를 만들어 경로마다 지급액을 계산하고 할인해 평균하는 방식으로 평가했습니다." />
      <div className="grid g2">
        <Card title="계약 조건 (Term Sheet)" right={<Badge label="MANUAL SCENARIO" />}>
          <div className="form">
            <Field label="6개월 조기상환 배리어 %" value={f.b1} onChange={(v) => set("b1", v)} />
            <Field label="12개월 배리어 %" value={f.b2} onChange={(v) => set("b2", v)} />
            <Field label="18개월 배리어 %" value={f.b3} onChange={(v) => set("b3", v)} />
            <Field label="만기 배리어 %" value={f.mb} onChange={(v) => set("mb", v)} />
            <Field label="낙인 배리어 %" value={f.ki} onChange={(v) => set("ki", v)} />
            <Field label="쿠폰 연 %" value={f.coupon} step={0.5} onChange={(v) => set("coupon", v)} />
            <Field label="수량 (매도 -)" value={f.qty} onChange={(v) => set("qty", v)} />
          </div>
          <p className="note">원금 $1,000 · 만기 2년 · 기준가는 평가 기준일 현물가 · 원금 비보장. 배리어는 기준가 대비 비율.</p>
        </Card>
        <Card title="모형 입력" right={<Badge label={edited ? "MANUAL SCENARIO" : snap.mode} />}>
          <div className="form">
            <Field label="SPY 현물가" value={f.s1} onChange={(v) => set("s1", v)} /><Field label="QQQ 현물가" value={f.s2} onChange={(v) => set("s2", v)} />
            <Field label="SPY 변동성 %" value={f.v1} onChange={(v) => set("v1", v)} /><Field label="QQQ 변동성 %" value={f.v2} onChange={(v) => set("v2", v)} />
            <Field label="SPY 배당률 %" value={f.q1} onChange={(v) => set("q1", v)} /><Field label="QQQ 배당률 %" value={f.q2} onChange={(v) => set("q2", v)} />
            <Field label="금리 %" value={f.r} step={0.1} onChange={(v) => set("r", v)} /><Field label="상관계수" value={f.rho} step={0.05} onChange={(v) => set("rho", v)} />
          </div>
          <div className="row"><button className="b" onClick={price} disabled={pr.loading}>Monte Carlo 평가 실행 ({nPaths.toLocaleString()} 경로)</button>
            <button className="b sec" onClick={() => { setF(init()); setEdited(false); }}>스냅샷 값으로 되돌리기</button></div>
        </Card>
      </div>
      <div className="row" style={{ margin: "0 0 12px" }}>
        <button className={"b " + (tab === "design" ? "" : "sec")} onClick={() => setTab("design")}>A. 지급 규칙</button>
        <button className={"b " + (tab === "price" ? "" : "sec")} onClick={() => setTab("price")}>B. 평가와 위험</button>
      </div>
      {tab === "design" && <>
        <div className="grid g2">
          <Card title="지급 규칙 (W = 두 자산의 기준가 대비 비율 중 낮은 값)">
            <div className="flow">
              {[["6개월", f.b1, 0.5], ["12개월", f.b2, 1.0], ["18개월", f.b3, 1.5]].map(([n, b, t]: any, k) => <div key={k}><b>{k + 1}</b>{n} 관측일에 W ≥ {b}% 이면 {usd(1000 * (1 + c * t), 0)} 지급 후 종료. 아니면 다음 단계</div>)}
              <div><b>4</b>만기(24개월)에 W ≥ {f.mb}% 이면 {usd(1000 * (1 + c * 2), 0)} 지급</div>
              <div><b>5</b>만기에 W &lt; {f.mb}% 이지만 기간 중 W가 {f.ki}% 이하로 내려간 적이 없으면 {usd(1000 * (1 + c * 2), 0)} 지급</div>
              <div><b>6</b>기간 중 W가 {f.ki}% 이하로 내려간 적이 있고(낙인) 만기에 W &lt; {f.mb}% 이면 $1,000 × W 지급 (원금 손실)</div>
            </div>
            <p className="note">쿠폰은 중간 지급 없이 상환 시점에 연 {f.coupon}% 단리로 한 번에 지급. 낙인은 매일 종가로 관측. 조기상환 이후의 가격은 영향을 주지 않음.</p>
          </Card>
          <Card title="예시 경로 4개 (지급 함수의 실제 계산 결과)" right={<Badge label="MANUAL SCENARIO" />}>
            <Err e={ex.error} />{ex.loading && <Loading />}
            {ex.data && <table><thead><tr><th>경로</th><th>지급액</th><th>원금 대비</th><th>상환 시점</th><th className="l">낙인</th></tr></thead><tbody>
              {ex.data.examples.map((e: any) => <tr key={e.id}><td>{e.name}</td><td>{usd(e.result.amount)}</td><td><Signed v={e.result.pnl_vs_notional} /></td><td>{e.result.redeem_time}년</td><td className="l">{e.result.knocked_in ? "발생" : "없음"}</td></tr>)}
            </tbody></table>}
            {ex.data && <ResponsiveContainer width="100%" height={200}><LineChart><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="t" type="number" domain={[0, 2]} {...axis} ticks={[0, 0.5, 1, 1.5, 2]} /><YAxis {...axis} width={40} domain={[0.4, 1.1]} tickFormatter={(v) => fmt(v * 100, 0)} />
              <Tooltip {...chartTip} formatter={(v: any) => fmt(v * 100, 1) + "%"} labelFormatter={(v) => v + "년"} />
              <ReferenceLine y={f.ki / 100} stroke="var(--neg)" strokeDasharray="4 3" label={{ value: "낙인", fill: "var(--neg)", fontSize: 10, position: "insideBottomLeft" }} />
              <ReferenceLine y={f.mb / 100} stroke="var(--mut)" strokeDasharray="4 3" />
              {ex.data.examples.map((e: any, k: number) => <Line key={e.id} data={e.result.path} name={e.name} dataKey="ratio1" stroke={`var(--chart${k + 1})`} dot={false} isAnimationActive={false} />)}
            </LineChart></ResponsiveContainer>}
            <p className="note">세로축은 W(%). 선은 설명용으로 그린 가상 경로이며 지급액은 계약 지급 함수가 계산함.</p>
          </Card>
        </div>
      </>}
      {tab === "price" && <>
        <Err e={pr.error} />{pr.loading && <Loading text="Monte Carlo 계산 중" />}
        {!p && !pr.loading && !pr.error && <p className="note">위의 평가 실행 버튼을 누르면 결과가 표시됨.</p>}
        {p && <>
          <div className="grid g4">
            <Kpi label="이론가 (투자자, 1개)" badge="MODEL ESTIMATE" value={usd(p.investor.price_per_note)} sub={`표준오차 ${fmt(p.investor.std_error)} · 95% 구간 ${fmt(p.investor.ci95[0])} ~ ${fmt(p.investor.ci95[1])}`} />
            <Kpi label="발행가 - 이론가" value={<Signed v={p.issuer_margin_per_note} />} sub="1개당. 헤지·조달 비용 미반영" />
            <Kpi label={`발행자 포지션 (${f.qty}개)`} value={<Signed v={p.issuer_position.mtm} />} sub="매도 포지션은 투자자 가치의 반대 부호" />
            <Kpi label="만기 손실 상환 비율" value={pct(p.distribution.loss_rate, 1)} sub={`낙인 경험 ${pct(p.distribution.knock_in_rate, 1)} · 평균 상환 ${fmt(p.distribution.avg_redeem_time)}년`} />
          </div>
          <div className="grid g2">
            <Card title="상환 유형별 경로 비율 (위험중립 모형 기준)">
              <ResponsiveContainer width="100%" height={230}><BarChart data={dist} layout="vertical" margin={{ left: 60 }}><CartesianGrid stroke="var(--line)" horizontal={false} />
                <XAxis type="number" {...axis} tickFormatter={(v) => v + "%"} /><YAxis type="category" dataKey="name" {...axis} width={110} />
                <Tooltip {...chartTip} formatter={(v: any) => fmt(v, 1) + "%"} /><Bar dataKey="pct" name="비율" fill="var(--chart1)" isAnimationActive={false} />
              </BarChart></ResponsiveContainer>
              <p className="note">비율 합계 {fmt(p.distribution.fraction_sum * 100, 1)}%. 표본 내 최저 지급액 {usd(p.distribution.min_payoff_in_sample)}. {p.distribution.note}</p>
            </Card>
            <Card title="표본 경로 25개의 W 추이 (%)">
              <ResponsiveContainer width="100%" height={230}><LineChart data={paths}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="t" type="number" domain={[0, 2]} ticks={[0, 0.5, 1, 1.5, 2]} {...axis} /><YAxis {...axis} width={40} domain={[30, 150]} allowDataOverflow />
                <ReferenceLine y={f.ki} stroke="var(--neg)" strokeDasharray="4 3" /><ReferenceLine y={f.mb} stroke="var(--mut)" strokeDasharray="4 3" /><ReferenceLine y={100} stroke="var(--line)" />
                {[0.5, 1, 1.5].map((t) => <ReferenceLine key={t} x={t} stroke="var(--line)" />)}
                {Array.from({ length: 25 }, (_, j) => <Line key={j} dataKey={"p" + j} stroke="var(--chart1)" strokeOpacity={0.35} dot={false} strokeWidth={1} isAnimationActive={false} />)}
              </LineChart></ResponsiveContainer>
              <p className="note">붉은 점선은 낙인 배리어, 회색 점선은 만기 배리어. 세로선은 조기상환 관측일.</p>
            </Card>
          </div>
          <div className="grid g2">
            <Card title="Greeks와 델타 헤지 수량" right={<Badge label="MODEL ESTIMATE" />}>
              <table><thead><tr><th>지표</th><th>SPY</th><th>QQQ</th><th className="l">단위</th></tr></thead><tbody>
                <tr><td>Delta (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.delta_1, 3)}</td><td>{fmt(p.greeks_investor_per_note.delta_2, 3)}</td><td className="wrap">기초자산 $1 상승 시 USD</td></tr>
                <tr><td>Gamma (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.gamma_1, 4)}</td><td>{fmt(p.greeks_investor_per_note.gamma_2, 4)}</td><td className="wrap">$1 상승 시 Delta 변화. 잡음 큼</td></tr>
                <tr><td>Vega (투자자 1개)</td><td>{fmt(p.greeks_investor_per_note.vega_1_per_1volpt)}</td><td>{fmt(p.greeks_investor_per_note.vega_2_per_1volpt)}</td><td className="wrap">변동성 +1%p 시 USD</td></tr>
                <tr><td>발행자 포지션 Delta</td><td><Signed v={p.issuer_position.delta_shares["1"]} unit="주" /></td><td><Signed v={p.issuer_position.delta_shares["2"]} unit="주" /></td><td className="wrap">수량 {f.qty}개 반영</td></tr>
                <tr><td>델타 중립 헤지 수량</td><td><Signed v={p.issuer_position.hedge_shares["1"]} unit="주" /></td><td><Signed v={p.issuer_position.hedge_shares["2"]} unit="주" /></td><td className="wrap">+ 매수, - 매도 (가상)</td></tr>
              </tbody></table>
              <p className="note">Rho(금리 +100bp, 투자자 1개): {fmt(p.greeks_investor_per_note.rho_per_100bp)} · Theta: N/A (발행 시점 평가 전용 범위)</p>
              <p className="note">현물 충격 폭별 Delta 추정: {p.bump_stability.map((b: any) => `${b.bump_pct}% → SPY ${fmt(b.delta_1, 3)}, QQQ ${fmt(b.delta_2, 3)}`).join(" · ")}</p>
            </Card>
            <Card title="충격 재평가 (투자자 1개 기준)">
              <table><thead><tr><th>조건</th><th>이론가</th><th>변화</th></tr></thead><tbody>
                <tr><td>두 자산 -10%</td><td>{usd(p.spot_shock.down_10pct.price)}</td><td><Signed v={p.spot_shock.down_10pct.change} /></td></tr>
                <tr><td>두 자산 +10%</td><td>{usd(p.spot_shock.up_10pct.price)}</td><td><Signed v={p.spot_shock.up_10pct.change} /></td></tr>
                <tr><td>상관계수 +0.10</td><td>{usd(p.corr_sensitivity.price_up)}</td><td><Signed v={p.corr_sensitivity.price_up - p.investor.price_per_note} /></td></tr>
                <tr><td>상관계수 -0.10</td><td>{usd(p.corr_sensitivity.price_down)}</td><td><Signed v={p.corr_sensitivity.price_down - p.investor.price_per_note} /></td></tr>
              </tbody></table>
              <p className="note">기준가는 고정하고 현재 현물가를 이동. 같은 난수로 평가. 상관계수 변화 시 손실 상환 비율: +0.10 → {pct(p.corr_sensitivity.loss_rate_up, 1)}, -0.10 → {pct(p.corr_sensitivity.loss_rate_down, 1)}</p>
              <div className="row"><button className="b sec" onClick={() => cv.run(() => send("/structuring/convergence", { spec, market, seed }))} disabled={cv.loading}>경로 수에 따른 수렴 확인</button></div>
              {cv.loading && <Loading />}
              {cv.data && <ResponsiveContainer width="100%" height={170}><LineChart data={cv.data.rows.map((r: any) => ({ ...r, n: String(r.n_paths), err: 1.96 * r.std_error }))}><CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="n" {...axis} /><YAxis {...axis} width={50} domain={["auto", "auto"]} tickFormatter={(v) => fmt(v, 0)} />
                <Tooltip {...chartTip} formatter={(v: any) => fmt(v)} /><Line dataKey="price" name="이론가" stroke="var(--chart1)" isAnimationActive={false}><ErrorBar dataKey="err" stroke="var(--mut)" width={4} /></Line>
              </LineChart></ResponsiveContainer>}
            </Card>
          </div>
          <Card title="관측 일정과 계산 조건">
            <table><thead><tr><th>회차</th><th>관측일</th><th>쿠폰 계산 연수</th><th>할인 연수(실제 일수/365)</th></tr></thead><tbody>
              {p.schedule.observation_dates.map((d: string, k: number) => <tr key={k}><td>{k < 3 ? `${k + 1}차 조기상환` : "만기"}</td><td>{d}</td><td>{p.schedule.coupon_year_fractions[k]}</td><td>{fmt(p.schedule.discount_year_fractions[k], 4)}</td></tr>)}
            </tbody></table>
            <ul className="note"><li>{p.schedule.rule}</li><li>경로 {p.n_paths.toLocaleString()}개 · 시드 {p.seed} · 대조 변수 사용 · 모형 {p.model_version} · 평가 기록 {p.valuation_id}</li>{p.warnings.map((w: string, k: number) => <li key={k}>{w}</li>)}</ul>
          </Card>
        </>}
      </>}
    </>
  );
}
