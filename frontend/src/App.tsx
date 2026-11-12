import { useEffect, useState } from "react";
import { get, send, STATIC } from "./api";
import { Badge, Err, Loading } from "./ui";
import GuidedDesk, { STEPS } from "./pages/GuidedDesk";
import Market from "./pages/Market";
import OptionLab from "./pages/OptionLab";
import Structuring from "./pages/Structuring";
import Portfolio from "./pages/Portfolio";
import Hedge from "./pages/Hedge";
import Stress from "./pages/Stress";

const PAGES: [string, string][] = [["market", "① 시장 데이터"], ["option", "② 옵션 가격결정"], ["struct", "③ 구조화상품"],
  ["book", "④ 포트폴리오 위험"], ["hedge", "⑤ 델타 헤지"], ["stress", "⑥ 스트레스 테스트"]];

export type Ctx = { snap: any; setSnap: (s: any) => void; nPaths: number; seed: number; bookVer: number; bumpBook: () => void };
/** 단일 거래 흐름의 공유 상태. 거래 시점 스냅샷과 장부 버전을 모든 단계가 함께 사용한다. */
export type Deal = { snap: any; source: "base" | "market" };

export default function App() {
  const [mode, setMode] = useState<"deal" | "desk">("deal");
  const [step, setStep] = useState(0);
  const [page, setPage] = useState("market");
  const [snap, setSnap] = useState<any>(null);
  const [deal, setDeal] = useState<Deal | null>(null);
  const [dealVer, setDealVer] = useState(0);
  const [err, setErr] = useState<any>(null);
  const [nPaths, setNPaths] = useState(20000);
  const [seed, setSeed] = useState(42);
  const [bookVer, setBookVer] = useState(0);

  const startDeal = (source: "base" | "market", marketSnap = snap) =>
    send("/deal/start", { source, snapshot_id: marketSnap.snapshot_id }).then((r) => { setDeal({ snap: r.snapshot, source }); setDealVer((v) => v + 1); }).catch(setErr);

  useEffect(() => {
    // 최초 실행: 실제 데이터 수집을 시도하고 실패 시 캐시, 합성 데이터 순으로 전환한다.
    send("/market/refresh", { mode: "auto" }).then((r) => r.snapshot).catch(() => get("/market/snapshot/active"))
      .then((s) => { setSnap(s); return startDeal("base", s); }).catch(setErr);
  }, []);

  const ctx: Ctx = { snap, setSnap, nPaths, seed, bookVer, bumpBook: () => setBookVer((v) => v + 1) };
  const cur = mode === "deal" ? deal?.snap : snap;
  const ready = snap && deal;
  return (
    <div className="app">
      <div className="top">
        <b>Mini S&T Front Office</b>
        <span className="seg">
          <button className={mode === "deal" ? "on" : ""} onClick={() => setMode("deal")}>기본</button>
          <button className={mode === "desk" ? "on" : ""} onClick={() => setMode("desk")}>고급</button>
        </span>
        {cur && <>
          <span className="kv"><span>DATA MODE</span><Badge label={cur.mode} /></span>
          <span className="kv"><span>기준일</span>{cur.as_of}</span>
          {cur.mode !== "MANUAL SCENARIO" && <span className="kv"><span>출처</span>{cur.quotes?.SPY?.source}</span>}
        </>}
      </div>
      <nav className="side">
        {mode === "deal"
          ? STEPS.map((n, k) => <button key={k} className={step === k ? "on" : ""} onClick={() => setStep(k)}>{n}</button>)
          : <>
            {PAGES.map(([k, n]) => <button key={k} className={page === k ? "on" : ""} onClick={() => setPage(k)}>{n}</button>)}
            <div className="set">
              <label>시뮬레이션 경로 수
                <select value={nPaths} onChange={(e) => setNPaths(Number(e.target.value))}>
                  {[5000, 20000, 50000, 100000].map((n) => <option key={n} value={n}>{n.toLocaleString()}</option>)}
                </select>
              </label>
              <label style={{ marginTop: 8 }}>난수 시드
                <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} />
              </label>
            </div>
          </>}
      </nav>
      <main>
        <Err e={err} />
        {!ready && !err && <Loading text={STATIC ? "계산 모듈 로딩 중 (최초 10초 내외)" : "시장 데이터 수집 중"} />}
        {ready && mode === "deal" && <GuidedDesk deal={deal!} ver={dealVer} bump={() => setDealVer((v) => v + 1)} step={step} setStep={setStep}
          start={(s) => startDeal(s)} openAdvanced={(p) => { setPage(p); setMode("desk"); }} />}
        {ready && mode === "desk" && <>
          {page === "market" && <Market {...ctx} />}
          {page === "option" && <OptionLab {...ctx} />}
          {page === "struct" && <Structuring {...ctx} />}
          {page === "book" && <Portfolio {...ctx} />}
          {page === "hedge" && <Hedge {...ctx} />}
          {page === "stress" && <Stress {...ctx} />}
        </>}
      </main>
    </div>
  );
}
