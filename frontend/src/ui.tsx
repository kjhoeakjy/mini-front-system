import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

export const UND = ["SPY", "QQQ"];

export function fmt(x: any, d = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "N/A";
  return Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
export const usd = (x: any, d = 2) => (x === null || x === undefined ? "N/A" : (x < 0 ? "-$" : "$") + fmt(Math.abs(x), d));
export const pct = (x: any, d = 2) => (x === null || x === undefined ? "N/A" : fmt(x * 100, d) + "%");
export function Signed({ v, d = 2, unit = "$" }: { v: any; d?: number; unit?: string }) {
  if (v === null || v === undefined) return <span className="mut">N/A</span>;
  const z = Math.abs(v) < 0.5 * Math.pow(10, -d);
  const s = z ? "" : v > 0 ? "+" : "-";
  return <span className={z ? "" : v > 0 ? "pos" : "neg"}>{s}{unit === "$" ? "$" : ""}{fmt(Math.abs(v), d)}{unit !== "$" ? unit : ""}</span>;
}

const BADGE: Record<string, string> = { "REAL MARKET DATA": "real", "CACHED REAL SNAPSHOT": "cached", "MANUAL SCENARIO": "manual", "SYNTHETIC DEMO": "synth", "MODEL ESTIMATE": "model" };
export function Badge({ label }: { label?: string }) {
  if (!label) return null;
  return <span className={"badge " + (BADGE[label] || "")}>{label}</span>;
}

export function Card({ title, children, right }: { title?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="card">
      {(title || right) && <h2 style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}><span>{title}</span><span>{right}</span></h2>}
      {children}
    </div>
  );
}

export function Kpi({ label, value, sub, badge }: { label: ReactNode; value: ReactNode; sub?: ReactNode; badge?: string }) {
  return (
    <div className="card kpi">
      <div className="l">{label}<Badge label={badge} /></div>
      <div className="v">{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

export function Field({ label, value, onChange, step, type = "number" }: { label: string; value: any; onChange: (v: any) => void; step?: number; type?: string }) {
  return (
    <label>{label}
      <input type={type} step={step} value={value ?? ""} onChange={(e) => onChange(type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)} />
    </label>
  );
}

export function Explain({ goal, read, missing, interview }: { goal: string[]; read: string[]; missing: string[]; interview: string }) {
  return (
    <details>
      <summary>학습 목표 · 결과 읽는 법 · 모형에서 빠진 요소 · 면접 설명</summary>
      <h3>학습 목표</h3><ul>{goal.map((t, i) => <li key={i}>{t}</li>)}</ul>
      <h3>결과 읽는 법</h3><ul>{read.map((t, i) => <li key={i}>{t}</li>)}</ul>
      <h3>이 모형에서 빠진 현실 요소</h3><ul>{missing.map((t, i) => <li key={i}>{t}</li>)}</ul>
      <h3>면접에서의 설명</h3><p>{interview}</p>
    </details>
  );
}

export function Err({ e }: { e: any }) {
  return e ? <div className="err">오류: {String(e.message || e)}<br /><span className="mut">입력값을 확인하거나 시장 화면에서 스냅샷을 다시 불러온 뒤 재시도</span></div> : null;
}
export const Loading = ({ text = "계산 중" }: { text?: string }) => <div className="loading">{text}…</div>;

/** 비동기 계산 상태. 재계산 중에는 이전 결과를 비워 과거 숫자가 새 값처럼 보이지 않게 한다. */
export function useAsync<T = any>() {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<any>(null);
  const seq = useRef(0);
  const run = useCallback((fn: () => Promise<T>) => {
    const id = ++seq.current;
    setLoading(true); setError(null); setData(null);
    return fn().then((d) => { if (id === seq.current) { setData(d); setLoading(false); } return d; })
      .catch((e) => { if (id === seq.current) { setError(e); setLoading(false); } });
  }, []);
  return { data, loading, error, run, setData };
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [JSON.stringify(value), ms]);
  return v;
}

export const CAT_KR: Record<string, string> = {
  AUTOCALL_1: "1차 조기상환", AUTOCALL_2: "2차 조기상환", AUTOCALL_3: "3차 조기상환", AUTOCALL_4: "4차 조기상환", AUTOCALL_5: "5차 조기상환",
  MATURITY_ABOVE_BARRIER: "만기 상환(배리어 이상)", MATURITY_NO_KNOCK_IN: "만기 상환(낙인 없음)", MATURITY_LOSS: "만기 손실 상환",
};
export const chartTip = { contentStyle: { background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }, labelStyle: { color: "var(--mut)" } };
export const axis = { stroke: "var(--mut)", fontSize: 11, tickLine: false };
