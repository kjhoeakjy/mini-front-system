"""Mini S&T Front Office API. 교육용 로컬 프로그램이며 실제 주문 기능은 없다."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import hedge, market, portfolio, pricing, stress, structuring

VERSION = "0.1.0"
STATIC = Path(__file__).resolve().parent / "static"

try:  # .env의 FRED_API_KEY 등을 읽는다. 값은 화면이나 로그에 출력하지 않는다.
    import os
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
except Exception:
    pass

app = FastAPI(title="Mini S&T Front Office", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "trading": "disabled", "purpose": "교육용. 실제 주문 기능 없음"}


for r in (market.router, pricing.router, structuring.router, portfolio.router, hedge.router, stress.router):
    v1.include_router(r)
app.include_router(v1)

if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if path and f.is_file() else STATIC / "index.html")
