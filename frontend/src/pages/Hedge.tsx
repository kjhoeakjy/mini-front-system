import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, fmt, Loading, pct, Signed, UND, usd, useAsync } from "../ui";

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
      <h1>⑤ 델타 헤지</h1>
      <Err e={plan.error} />{plan.loading && <Loading text="순 Delta 산출 중" />}
      {p && <>
        <Card title="델타 헤지 제안">
          <div className="tw"><table>
            <thead><tr><th>기초자산</th><th>순 Delta</th><th>제안 거래</th><th>거래 후 보유</th><th>잔여 Delta</th><th>+1% 손익 (전 / 후)</th><th>거래 비용</th></tr></thead>
            <tbody>{UND.map((u) => { const x = p.plan[u]; return <tr key={u}><td>{u}</td><td><Signed v={x.net_delta_before} unit="주" /></td>
              <td><b>{x.side}{x.trade_shares !== 0 ? ` ${fmt(Math.abs(x.trade_shares), intShares ? 0 : 2)}주` : ""}</b></td><td>{fmt(x.shares_after, intShares ? 0 : 2)}주</td><td><Signed v={x.net_delta_after} unit="주" /></td>
              <td><Signed v={x.pnl_1pct_up_before} /> / <Signed v={x.pnl_1pct_up_after} /></td>
              <td>{usd(x.estimated_cost)}</td></tr>; })}</tbody>
          </table></div>
          <div className="row">
            <button className="b" onClick={apply} disabled={none}>가상 헤지 적용</button>
            <label style={{ width: 150 }}>거래 비용 (bp)<input type="number" value={cost} step={0.5} onChange={(e) => setCost(Number(e.target.value) || 0)} /></label>
            <label style={{ width: 150 }}>수량 단위<select value={intShares ? "1" : "0"} onChange={(e) => setIntShares(e.target.value === "1")}><option value="1">정수 주식</option><option value="0">소수점 허용</option></select></label>
          </div>
        </Card>
        {trades.length > 0 && <div style={{ marginTop: 12 }}><Card title="가상 거래 내역">
          <table><thead><tr><th>시각</th><th>기초자산</th><th>수량</th><th>체결가</th><th>거래 비용</th></tr></thead><tbody>
            {trades.map((t) => <tr key={t.id}><td>{new Date(t.created_at).toLocaleString("ko-KR")}</td><td>{t.underlying}</td><td><Signed v={t.shares} unit="주" d={0} /></td><td>{usd(t.price)}</td><td>{usd(t.cost)}</td></tr>)}
          </tbody></table></Card></div>}
      </>}
      <div style={{ marginTop: 12 }}>
        <Card title="동적 헤지 시뮬레이션 (콜 1계약 매도)">
          <div className="row" style={{ marginTop: 0 }}>
            <label style={{ width: 120 }}>기초자산<select value={ticker} onChange={(e) => setTicker(e.target.value)}><option>SPY</option><option>QQQ</option></select></label>
            <button className="b" onClick={() => bt.run(() => send("/hedge/backtest", { snapshot_id: snap.snapshot_id, ticker, cost_bps: cost }))} disabled={bt.loading}>최근 6개월 실행</button>
          </div>
          <Err e={bt.error} />{bt.loading && <Loading />}
          {bt.data && <>
            <table><thead><tr><th>재헤지 주기</th><th>최종 손익</th><th>거래 횟수</th><th>거래 비용</th><th>수취 프리미엄</th><th>만기 지급액</th></tr></thead><tbody>
              {bt.data.runs.map((r: any) => <tr key={r.name}><td>{r.name}</td><td><Signed v={r.final_pnl} /></td><td>{r.n_trades}</td><td>{usd(r.total_cost)}</td><td>{usd(r.premium)}</td><td>{usd(r.payoff_at_expiry)}</td></tr>)}
            </tbody></table>
            <ResponsiveContainer width="100%" height={240}><LineChart data={series}><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="date" {...axis} minTickGap={50} /><YAxis {...axis} width={55} tickFormatter={(v) => fmt(v, 0)} />
              <Tooltip {...chartTip} formatter={(v: any) => usd(v)} /><Legend />
              {bt.data.runs.map((r: any, k: number) => <Line key={r.name} dataKey={r.name} stroke={`var(--chart${k + 1})`} dot={false} isAnimationActive={false} />)}
            </LineChart></ResponsiveContainer>
          </>}
        </Card>
      </div>
    </>
  );
}
