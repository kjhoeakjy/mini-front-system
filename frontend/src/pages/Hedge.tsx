import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, Explain, fmt, Loading, pct, Signed, UND, usd, useAsync } from "../ui";

export default function Hedge({ snap, nPaths, seed, bookVer, bumpBook }: Ctx) {
  const plan = useAsync(), bt = useAsync();
  const [cost, setCost] = useState(1);
  const [intShares, setIntShares] = useState(true);
  const [trades, setTrades] = useState<any[]>([]);
  const [ticker, setTicker] = useState("SPY");
  const body = { snapshot_id: snap.snapshot_id, n_paths: nPaths, seed, cost_bps: cost, integer_shares: intShares };
  const load = () => { plan.run(() => send("/hedge/delta", body)); get("/book").then((b) => setTrades(b.hedge_trades)); };
  useEffect(() => { load(); }, [snap.snapshot_id, nPaths, seed, bookVer, cost, intShares]);
  const apply = () => send("/hedge/delta", { ...body, apply: true }).then(bumpBook);
  const p = plan.data;
  const series = bt.data ? bt.data.runs[0].rows.map((row: any, k: number) => { const o: any = { date: row.date, spot: row.spot }; bt.data.runs.forEach((r: any) => { o[r.name] = r.rows[k].pnl; }); return o; }) : [];
  const none = p && UND.every((u) => p.plan[u].trade_shares === 0);
  return (
    <>
      <h1>⑤ 헤지 Hedging Simulator</h1>
      <p className="sub">장부의 순 Delta를 0에 가깝게 만드는 가상 주식 거래 수량. 실제 주문은 내지 않음</p>
      <Explain goal={["순 Delta의 반대 수량만큼 기초자산을 거래하면 Delta가 0에 가까워짐을 확인", "한 번 맞춘 뒤에도 다시 맞춰야 하는 이유 이해"]}
        read={["거래 수량 = -(순 Delta). 음수 Delta면 매수, 양수 Delta면 매도", "정수 주식으로 거래하면 소수점 이하의 잔여 Delta가 남음", "아래 시뮬레이션에서 재헤지 주기에 따른 손익 변동과 비용을 비교"]}
        missing={["실제 체결가, 호가 스프레드, 시장 충격", "장중 급변(갭)", "노트의 시간 경과에 따른 재헤지"]}
        interview="주가의 작은 움직임에 대한 일차 위험은 반대 포지션으로 줄일 수 있습니다. 다만 가격이 움직이면 델타가 변하므로 계속 다시 맞춰야 하고, 변동성이나 감마 위험까지 없어지는 것은 아닙니다." />
      <Err e={plan.error} />{plan.loading && <Loading text="장부 Delta 계산 중" />}
      {p && <>
        <Card title="델타 헤지 제안" right={<><Badge label="MODEL ESTIMATE" /> <span className="mut">{p.order_notice}</span></>}>
          <div className="tw"><table>
            <thead><tr><th>기초자산</th><th>헤지 전 순 Delta</th><th>제안 거래</th><th>거래 후 보유 주식</th><th>헤지 후 순 Delta</th><th>달러 Delta 전 → 후</th><th>+1% 손익 전 → 후</th><th>-1% 손익 전 → 후</th><th>예상 비용</th></tr></thead>
            <tbody>{UND.map((u) => { const x = p.plan[u]; return <tr key={u}><td>{u}</td><td><Signed v={x.net_delta_before} unit="주" /></td>
              <td><b>{x.side}{x.trade_shares !== 0 ? ` ${fmt(Math.abs(x.trade_shares), intShares ? 0 : 2)}주` : ""}</b></td><td>{fmt(x.shares_after, intShares ? 0 : 2)}주</td><td><Signed v={x.net_delta_after} unit="주" /></td>
              <td><Signed v={x.dollar_delta_before} d={0} /> → <Signed v={x.dollar_delta_after} d={0} /></td><td><Signed v={x.pnl_1pct_up_before} /> → <Signed v={x.pnl_1pct_up_after} /></td>
              <td><Signed v={x.pnl_1pct_dn_before} /> → <Signed v={x.pnl_1pct_dn_after} /></td><td>{usd(x.estimated_cost)}</td></tr>; })}</tbody>
          </table></div>
          <div className="row">
            <button className="b" onClick={apply} disabled={none}>가상 헤지 적용 (장부의 현물 수량만 변경)</button>
            <label style={{ width: 150 }}>거래 비용 (bp)<input type="number" value={cost} step={0.5} onChange={(e) => setCost(Number(e.target.value) || 0)} /></label>
            <label style={{ width: 150 }}>수량 단위<select value={intShares ? "1" : "0"} onChange={(e) => setIntShares(e.target.value === "1")}><option value="1">정수 주식</option><option value="0">소수점 허용</option></select></label>
          </div>
          {none && <p className="note">현재 순 Delta가 반올림 범위 안이므로 추가 거래가 없음.</p>}
          <ul className="note">{p.messages.map((m: string, k: number) => <li key={k}>{m}</li>)}</ul>
          <p className="note">헤지 후에도 남는 위험 · Gamma: SPY {fmt(p.remaining.gamma.SPY, 3)}, QQQ {fmt(p.remaining.gamma.QQQ, 3)} · Vega: SPY {usd(p.remaining.vega.SPY)}, QQQ {usd(p.remaining.vega.QQQ)} · Rho: {usd(p.remaining.rho)}</p>
        </Card>
        {trades.length > 0 && <div style={{ marginTop: 12 }}><Card title="가상 거래 기록">
          <table><thead><tr><th>시각</th><th>기초자산</th><th>수량</th><th>가정 체결가</th><th>비용</th></tr></thead><tbody>
            {trades.map((t) => <tr key={t.id}><td>{new Date(t.created_at).toLocaleString("ko-KR")}</td><td>{t.underlying}</td><td><Signed v={t.shares} unit="주" d={0} /></td><td>{usd(t.price)}</td><td>{usd(t.cost)}</td></tr>)}
          </tbody></table></Card></div>}
      </>}
      <div style={{ marginTop: 12 }}>
        <Card title="시간에 따른 재헤지 시뮬레이션 (유럽형 콜 1계약 매도)" right={<Badge label={snap.quotes[ticker].label} />}>
          <div className="row" style={{ marginTop: 0 }}>
            <label style={{ width: 120 }}>기초자산<select value={ticker} onChange={(e) => setTicker(e.target.value)}><option>SPY</option><option>QQQ</option></select></label>
            <button className="b" onClick={() => bt.run(() => send("/hedge/backtest", { snapshot_id: snap.snapshot_id, ticker, cost_bps: cost }))} disabled={bt.loading}>최근 약 6개월 가격으로 실행</button>
          </div>
          <Err e={bt.error} />{bt.loading && <Loading />}
          {bt.data && <>
            <p className="note">{bt.data.start} ~ {bt.data.end} · 변동성 {pct(bt.data.sigma, 1)} ({bt.data.sigma_source}) · 금리 {pct(bt.data.rate)}</p>
            <table><thead><tr><th>재헤지 주기</th><th>최종 손익</th><th>거래 횟수</th><th>거래 비용 합계</th><th>수취 프리미엄</th><th>만기 지급액</th></tr></thead><tbody>
              {bt.data.runs.map((r: any) => <tr key={r.name}><td>{r.name}</td><td><Signed v={r.final_pnl} /></td><td>{r.n_trades}</td><td>{usd(r.total_cost)}</td><td>{usd(r.premium)}</td><td>{usd(r.payoff_at_expiry)}</td></tr>)}
            </tbody></table>
            <ResponsiveContainer width="100%" height={240}><LineChart data={series}><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="date" {...axis} minTickGap={50} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
              <Tooltip {...chartTip} formatter={(v: any) => usd(v)} /><Legend />
              {bt.data.runs.map((r: any, k: number) => <Line key={r.name} dataKey={r.name} stroke={`var(--chart${k + 1})`} dot={false} isAnimationActive={false} />)}
            </LineChart></ResponsiveContainer>
            <ul className="note"><li>세로축은 누적 손익(현금 + 보유 주식 평가액 - 옵션 부채). 자주 헤지할수록 손익 변동은 줄고 거래 비용은 늘어남.</li>{bt.data.assumptions.map((a: string, k: number) => <li key={k}>{a}</li>)}</ul>
          </>}
        </Card>
      </div>
    </>
  );
}
