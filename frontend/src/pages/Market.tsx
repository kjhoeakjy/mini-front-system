import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, send } from "../api";
import type { Ctx } from "../App";
import { axis, Badge, Card, chartTip, Err, Explain, Field, fmt, Kpi, Loading, pct, UND, usd, useAsync } from "../ui";

export default function Market({ snap, setSnap, bumpBook }: Ctx) {
  const [status, setStatus] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [list, setList] = useState<any[]>([]);
  const [hist, setHist] = useState<any[]>([]);
  const [m, setM] = useState<any>({});
  const chain = useAsync();
  const i = snap.inputs;

  useEffect(() => {
    get("/market/snapshots").then((r) => setList(r.snapshots));
    Promise.all(UND.map((u) => get(`/market/history/${u}?snapshot_id=${snap.snapshot_id}`))).then(([a, b]) => {
      const a0 = a.rows[0].adj_close, b0 = b.rows[0].adj_close;
      setHist(a.rows.map((r: any, k: number) => ({ date: r.date, SPY: (r.adj_close / a0) * 100, QQQ: (b.rows[k].adj_close / b0) * 100 })));
    });
    setM({ sSPY: i.spots.SPY.value, sQQQ: i.spots.QQQ.value, vSPY: +(i.vols.SPY.value * 100).toFixed(2), vQQQ: +(i.vols.QQQ.value * 100).toFixed(2),
      qSPY: +(i.divs.SPY.value * 100).toFixed(2), qQQQ: +(i.divs.QQQ.value * 100).toFixed(2), rate: +(i.curve[i.curve.length - 1].value * 100).toFixed(2), corr: +i.corr.value.toFixed(3) });
    chain.setData(null);
  }, [snap.snapshot_id]);

  const refresh = (mode: string) => {
    setBusy(true); setErr(null);
    send("/market/refresh", { mode }).then((r) => { setSnap(r.snapshot); setStatus(r.status); }).catch(setErr).finally(() => setBusy(false));
  };
  const applyManual = () => {
    setErr(null);
    send("/market/manual", { base_snapshot_id: snap.snapshot_id, spots: { SPY: m.sSPY, QQQ: m.sQQQ }, vols: { SPY: m.vSPY / 100, QQQ: m.vQQQ / 100 },
      divs: { SPY: m.qSPY / 100, QQQ: m.qQQQ / 100 }, rate: m.rate / 100, corr: m.corr }).then((r) => setSnap(r.snapshot)).catch(setErr);
  };
  const pick = (id: string) => get(`/market/snapshot/${id}`).then(setSnap).catch(setErr);
  const resetBook = () => send("/book/reset", { snapshot_id: snap.snapshot_id }).then(() => { bumpBook(); setStatus([{ step: "장부", ok: true, message: "현재 스냅샷의 현물가를 행사가·기준가로 하여 기본 장부를 다시 만듦" }]); }).catch(setErr);

  return (
    <>
      <h1>① 시장 Market Overview</h1>
      <p className="sub">평가에 쓰는 입력값의 출처, 관측 시점, 품질을 확인하는 화면</p>
      <Explain goal={["모형 입력(현물가, 변동성, 금리, 배당, 상관계수)이 어디서 오는지 구분", "실제 자료와 가정값의 차이 확인"]}
        read={["각 값 옆 표기로 실제 자료·캐시·수동 입력·가상 자료·모형 추정을 구분", "변동성과 상관계수는 과거 가격으로 계산한 대용치"]}
        missing={["실시간 호가, 변동성 곡면, 만기별 할인곡선", "거래소 휴장일 달력"]}
        interview="정확한 모형도 입력 자료가 틀리면 잘못된 가격을 냅니다. 그래서 관측 시점과 자료 품질을 먼저 확인하도록 구성했습니다." />
      <Err e={err} />
      <div className="grid g4">
        {UND.map((u) => <Kpi key={u} label={`${u} 현물가`} badge={i.spots[u].label} value={usd(i.spots[u].value)} sub={`${snap.quotes[u].trade_date} ${snap.quotes[u].price_type} · ${snap.quotes[u].source}`} />)}
        {UND.map((u) => <Kpi key={u + "v"} label={`${u} 변동성 (연율)`} badge={i.vols[u].label} value={pct(i.vols[u].value)} sub="실현변동성 252일. 내재변동성의 대용치" />)}
        <Kpi label="상관계수" badge={i.corr.label} value={fmt(i.corr.value, 3)} sub={`최근 ${i.corr.n_obs}거래일 로그수익률`} />
        <Kpi label="금리 (2년)" badge={i.curve[i.curve.length - 1].label} value={pct(i.curve[i.curve.length - 1].value)} sub="국채 수익률을 평탄 금리로 근사" />
      </div>
      <div className="grid g2">
        <Card title="자료 불러오기">
          <div className="row" style={{ marginTop: 0 }}>
            <button className="b" disabled={busy} onClick={() => refresh("auto")}>실제 자료 새로고침</button>
            <button className="b sec" disabled={busy} onClick={() => refresh("synthetic")}>가상 자료 사용</button>
            <button className="b sec" onClick={resetBook}>이 스냅샷으로 장부 초기화</button>
          </div>
          {busy && <Loading text="수집 중" />}
          {status.map((s, k) => <div key={k} className={s.ok ? "note" : "note neg"}>{s.ok ? "성공" : "실패"} · {s.step}: {s.message}</div>)}
          <p className="note">실제 자료는 yfinance(시세)와 FRED(금리)에서 받음. 실패하면 저장된 실제 스냅샷, 그다음 가상 자료 순으로 전환함.</p>
          <label style={{ marginTop: 10 }}>저장된 스냅샷
            <select value={snap.snapshot_id} onChange={(e) => pick(e.target.value)}>
              {list.find((s) => s.id === snap.snapshot_id) ? null : <option value={snap.snapshot_id}>{snap.as_of} · {snap.mode}</option>}
              {list.map((s) => <option key={s.id} value={s.id}>{s.as_of} · {s.mode} · {new Date(s.created_at).toLocaleString("ko-KR")}</option>)}
            </select>
          </label>
          <div className="row"><a href={`/api/v1/market/snapshot/${snap.snapshot_id}/export`} target="_blank" rel="noreferrer" style={{ color: "var(--acc)" }}>스냅샷 JSON 내보내기</a></div>
          {(snap.quality_flags.length > 0 || snap.warnings.length > 0) && <ul className="note warn">{[...snap.quality_flags, ...snap.warnings].map((w: string, k: number) => <li key={k}>{w}</li>)}</ul>}
        </Card>
        <Card title="수동 입력 (MANUAL SCENARIO)">
          <div className="form">
            <Field label="SPY 현물가" value={m.sSPY} onChange={(v) => setM({ ...m, sSPY: v })} />
            <Field label="QQQ 현물가" value={m.sQQQ} onChange={(v) => setM({ ...m, sQQQ: v })} />
            <Field label="SPY 변동성 %" value={m.vSPY} onChange={(v) => setM({ ...m, vSPY: v })} />
            <Field label="QQQ 변동성 %" value={m.vQQQ} onChange={(v) => setM({ ...m, vQQQ: v })} />
            <Field label="SPY 배당률 %" value={m.qSPY} onChange={(v) => setM({ ...m, qSPY: v })} />
            <Field label="QQQ 배당률 %" value={m.qQQQ} onChange={(v) => setM({ ...m, qQQQ: v })} />
            <Field label="금리 % (전 만기)" value={m.rate} onChange={(v) => setM({ ...m, rate: v })} />
            <Field label="상관계수" value={m.corr} step={0.01} onChange={(v) => setM({ ...m, corr: v })} />
          </div>
          <div className="row"><button className="b" onClick={applyManual}>수동 값으로 새 스냅샷 만들기</button></div>
          <p className="note">원본 스냅샷은 그대로 두고 새 스냅샷을 만듦. 이후 장부·헤지·스트레스 화면이 이 값으로 다시 계산됨. 계약의 행사가와 기준가는 바뀌지 않음.</p>
        </Card>
      </div>
      <div className="grid g2">
        <Card title="금리 · 배당 · 변동성 상세">
          <div className="tw"><table>
            <thead><tr><th>항목</th><th>값</th><th className="l">표기</th><th className="l">출처·방법</th></tr></thead>
            <tbody>
              {i.curve.map((p: any) => <tr key={p.series}><td>{p.series} ({p.tenor_years}년)</td><td>{pct(p.value)}</td><td className="l"><Badge label={p.label} /></td><td className="wrap">{p.source}{p.observed_date ? ` · 관측일 ${p.observed_date}` : ""} · 근사</td></tr>)}
              {UND.map((u) => <tr key={u}><td>{u} 배당수익률</td><td>{pct(i.divs[u].value)}</td><td className="l"><Badge label={i.divs[u].label} /></td><td className="wrap">{i.divs[u].source}</td></tr>)}
              {UND.map((u) => <tr key={u + "rv"}><td>{u} 실현변동성 20/60/252일</td><td>{["20", "60", "252"].map((w) => pct(snap.realized_vol[u][w], 1)).join(" / ")}</td><td className="l"><Badge label={i.vols[u].label} /></td><td className="wrap">{i.vols[u].source}</td></tr>)}
              <tr><td>상관계수</td><td>{fmt(i.corr.value, 3)}</td><td className="l"><Badge label={i.corr.label} /></td><td className="wrap">{i.corr.source}</td></tr>
            </tbody>
          </table></div>
          <p className="note">{snap.rate_method}</p>
        </Card>
        <Card title="조정종가 추이 (시작일 = 100)" right={<Badge label={snap.quotes.SPY.label} />}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={hist}><CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="date" {...axis} minTickGap={60} /><YAxis {...axis} domain={["auto", "auto"]} width={40} />
              <Tooltip {...chartTip} formatter={(v: any) => fmt(v, 1)} /><Legend />
              <Line dataKey="SPY" stroke="var(--chart1)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
              <Line dataKey="QQQ" stroke="var(--chart2)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <Card title="상장 옵션 호가와 유럽형 모형 비교 (참고)" right={<button className="b sec" onClick={() => chain.run(() => get(`/market/options/SPY?snapshot_id=${snap.snapshot_id}`))}>SPY 옵션 체인 불러오기</button>}>
        {chain.loading && <Loading text="옵션 체인 수집 중" />}
        <Err e={chain.error} />
        {chain.data && !chain.data.available && <p className="note warn">사용 불가: {chain.data.reason}</p>}
        {chain.data?.available && <>
          <p className="note">만기 {chain.data.expiry} · {chain.data.source} · 수집 {chain.data.snapshot_time} <Badge label="REAL MARKET DATA" /></p>
          <div className="tw" style={{ maxHeight: 320, overflowY: "auto" }}><table>
            <thead><tr><th>행사가</th><th>구분</th><th>매수호가</th><th>매도호가</th><th>중간값</th><th>모형가(스냅샷 변동성)</th><th>역산 변동성(대용치)</th><th>공급자 IV</th><th className="l">상태</th></tr></thead>
            <tbody>{chain.data.rows.map((r: any, k: number) => <tr key={k}><td>{fmt(r.strike, 0)}</td><td>{r.option_type}</td><td>{fmt(r.bid)}</td><td>{fmt(r.ask)}</td><td>{fmt(r.mid)}</td><td>{fmt(r.model_price_snapshot_vol)}</td><td>{r.european_model_implied_proxy ? pct(r.european_model_implied_proxy, 1) : "IV unavailable"}</td><td>{pct(r.provider_iv, 1)}</td><td className="l mut">{[r.iv_status, ...r.quality_flags].join(", ")}</td></tr>)}</tbody>
          </table></div>
          <ul className="note">{chain.data.warnings.map((w: string, k: number) => <li key={k}>{w}</li>)}</ul>
        </>}
        {!chain.data && !chain.loading && <p className="note">상장 SPY 옵션은 미국형이므로 유럽형 BSM 값과 일치하지 않음. 비교와 변동성 수준 확인 용도.</p>}
      </Card>
    </>
  );
}
