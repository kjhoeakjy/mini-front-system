import { useEffect, useState } from "react";
import { get, send } from "./api";
import { Badge, Err, Loading } from "./ui";
import Market from "./pages/Market";
import OptionLab from "./pages/OptionLab";
import Structuring from "./pages/Structuring";
import Portfolio from "./pages/Portfolio";
import Hedge from "./pages/Hedge";
import Stress from "./pages/Stress";

const PAGES: [string, string][] = [["market", "① 시장 Market"], ["option", "② 옵션 Option Pricing"], ["struct", "③ 구조화 Structuring"],
  ["book", "④ 장부 Portfolio & Risk"], ["hedge", "⑤ 헤지 Hedging"], ["stress", "⑥ 스트레스 Stress"]];

export type Ctx = { snap: any; setSnap: (s: any) => void; nPaths: number; seed: number; bookVer: number; bumpBook: () => void };

export default function App() {
  const [page, setPage] = useState("market");
  const [snap, setSnap] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [nPaths, setNPaths] = useState(20000);
  const [seed, setSeed] = useState(42);
  const [bookVer, setBookVer] = useState(0);
  const [theme, setTheme] = useState("dark");

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => {
    // 첫 실행: 실제 자료를 시도하고 실패하면 캐시, 그다음 가상 자료 순으로 전환한다.
    send("/market/refresh", { mode: "auto" }).then((r) => setSnap(r.snapshot)).catch(() => get("/market/snapshot/active").then(setSnap).catch(setErr));
  }, []);

  const ctx: Ctx = { snap, setSnap, nPaths, seed, bookVer, bumpBook: () => setBookVer((v) => v + 1) };
  const q = snap?.quotes?.SPY;
  return (
    <div className="app">
      <div className="top">
        <b>Mini S&T Front Office</b>
        {snap && <>
          <span className="kv"><span>DATA MODE</span><Badge label={snap.mode} /></span>
          <span className="kv"><span>기준일(as-of)</span>{snap.as_of} 종가</span>
          <span className="kv"><span>스냅샷 생성</span>{new Date(snap.created_at).toLocaleString("ko-KR")} KST</span>
          <span className="kv"><span>출처</span>{q?.source}</span>
          <span className="kv"><span>미국 정규장</span>{snap.market_status?.regular_session_open ? "개장" : "마감"}</span>
          <span className="kv"><span>평가 모형</span>BSM · MC-GBM</span>
        </>}
        <button className="b sec" style={{ marginLeft: "auto", padding: "3px 8px" }} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "밝은 화면" : "어두운 화면"}</button>
      </div>
      <div className="banner">교육용 프로그램. 투자 권유가 아니며 실제 호가·주문 시스템이 아님. 모든 계약은 가상이며 결과는 단순화한 모형의 추정값임.</div>
      <nav className="side">
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
      </nav>
      <main>
        <Err e={err} />
        {!snap && !err && <Loading text="시장 자료 불러오는 중" />}
        {snap && page === "market" && <Market {...ctx} />}
        {snap && page === "option" && <OptionLab {...ctx} />}
        {snap && page === "struct" && <Structuring {...ctx} />}
        {snap && page === "book" && <Portfolio {...ctx} />}
        {snap && page === "hedge" && <Hedge {...ctx} />}
        {snap && page === "stress" && <Stress {...ctx} />}
      </main>
    </div>
  );
}
