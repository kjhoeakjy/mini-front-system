const BASE = "/api/v1";
// pages 모드: 서버 없이 브라우저 안의 Python 실행기(Web Worker)로 같은 API를 호출한다.
export const STATIC = import.meta.env.MODE === "pages";

let worker: Worker | null = null;
let seq = 0;
const pending = new Map<number, { ok: (v: any) => void; no: (e: any) => void }>();

function viaWorker(method: string, url: string, body?: string): Promise<any> {
  if (!worker) {
    worker = new Worker(new URL("./py-worker.js", document.baseURI));
    worker.onmessage = (e) => {
      const p = pending.get(e.data.id);
      if (!p) return;
      pending.delete(e.data.id);
      if (e.data.error) return p.no(new Error("계산 모듈 오류: " + e.data.error));
      const r = JSON.parse(e.data.res);
      let j: any = null;
      try { j = JSON.parse(r.body); } catch {}
      if (r.status >= 400) p.no(new Error(j?.detail ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : `요청 실패 (${r.status})`));
      else p.ok(j);
    };
    worker.onerror = (e) => { pending.forEach((p) => p.no(new Error("계산 모듈 로딩 실패: " + e.message))); pending.clear(); };
  }
  return new Promise((ok, no) => { const id = ++seq; pending.set(id, { ok, no }); worker!.postMessage({ id, method, url, body }); });
}

async function handle(r: Response) {
  if (!r.ok) {
    let msg = `요청 실패 (${r.status})`;
    try {
      const j = await r.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const get = (path: string) => (STATIC ? viaWorker("GET", BASE + path) : fetch(BASE + path).then(handle));
export const send = (path: string, body: any = {}, method = "POST") =>
  STATIC ? viaWorker(method, BASE + path, JSON.stringify(body))
    : fetch(BASE + path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(handle);

export function download(name: string, data: any) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
