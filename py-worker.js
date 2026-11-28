// 정적 배포용: 브라우저 안에서 Python 계산 코드를 실행한다(Pyodide). 서버 실행 시에는 사용하지 않는다.
importScripts("./pyodide/pyodide.js");

const ready = (async () => {
  const base = new URL("./", self.location.href).href;
  const py = await loadPyodide({ indexURL: base + "pyodide/" });
  await py.loadPackage(["numpy", "pydantic", "sqlite3", "tzdata", "ssl"]);
  const manifest = await (await fetch(base + "wheels/manifest.json")).json();
  for (const w of manifest) py.unpackArchive(await (await fetch(base + "wheels/" + w)).arrayBuffer(), "wheel");
  py.unpackArchive(await (await fetch(base + "backend.zip")).arrayBuffer(), "zip", { extractDir: "/home/pyodide/backend" });
  py.runPython('import sys, os\nsys.path.insert(0, "/home/pyodide/backend")\nos.environ["MINI_FO_DB"] = "/home/pyodide/app.db"');
  py.runPython("from app.pyodide_bridge import call");
  return py.globals.get("call");
})();

self.onmessage = async (e) => {
  const { id, method, url, body } = e.data;
  try {
    const call = await ready;
    postMessage({ id, res: await call(method, url, body ?? null) });
  } catch (err) {
    postMessage({ id, error: String(err) });
  }
};
