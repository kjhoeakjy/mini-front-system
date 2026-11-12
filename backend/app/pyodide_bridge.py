"""서버 없이 같은 API를 호출하기 위한 연결부(브라우저 내 Python 실행용).

FastAPI 앱을 ASGI 규약으로 직접 호출한다. 브라우저에는 스레드가 없으므로 동기 함수는 그 자리에서 실행한다.
"""
from __future__ import annotations

import json

import fastapi.routing

from .main import app


async def _inline(func, *args, **kwargs):
    return func(*args, **kwargs)


fastapi.routing.run_in_threadpool = _inline


async def call(method: str, url: str, body: str | None = None) -> str:
    path, _, query = url.partition("?")
    payload = (body or "").encode("utf-8")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method.upper(), "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
             "server": ("local", 80), "client": ("local", 0)}
    sent = False
    out = {"status": 500, "body": b""}

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    await app(scope, receive, send)
    return json.dumps({"status": out["status"], "body": out["body"].decode("utf-8")})
