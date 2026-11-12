import { useEffect, useState } from "react";
import { get, send, STATIC } from "./api";
import { Badge, Err, Loading } from "./ui";
import Market from "./pages/Market";
import OptionLab from "./pages/OptionLab";
import Structuring from "./pages/Structuring";
import Portfolio from "./pages/Portfolio";
import Hedge from "./pages/Hedge";
import Stress from "./pages/Stress";

const PAGES: [string, string][] = [["market", "① 시장 데이터"], ["option", "② 옵션 가격결정"], ["struct", "③ 구조화상품"],
  ["book", "④ 포트폴리오 위험"], ["hedge", "⑤ 델타 헤지"], ["stress", "⑥ 스트레스 테스트"]];

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
          <span className="kv"><span>기준일</span>{snap.as_of} 종가</span>
          <span className="kv"><span>출처</span>{q?.source}</span>
          <span className="kv"><span>평가 모형</span>BSM · Monte Carlo GBM</span>
        </>}
        <button className="b sec" style={{ marginLeft: "auto", padding: "3px 8px" }} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "밝은 화면" : "어두운 화면"}</button>
      </div>
      <div className="banner">교육용. 가상 계약 기준의 모형 추정값이며 실제 호가·주문 기능 없음.</div>
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
        {!snap && !err && <Loading text={STATIC ? "계산 모듈 로딩 중 (최초 10초 내외)" : "시장 데이터 수집 중"} />}
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
