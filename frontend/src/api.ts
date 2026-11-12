const BASE = "/api/v1";

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

export const get = (path: string) => fetch(BASE + path).then(handle);
export const send = (path: string, body: any = {}, method = "POST") =>
  fetch(BASE + path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(handle);
