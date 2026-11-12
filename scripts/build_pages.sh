#!/usr/bin/env bash
# 정적 배포본(site/) 생성. 화면 빌드 + Python 실행기(Pyodide) + 계산 코드 묶음.
# PYODIDE_DIR에 Pyodide 배포 파일이 있으면 그것을 쓰고, 없으면 GitHub 릴리스에서 받는다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYODIDE_VERSION=0.26.4
FILES="pyodide.js pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json numpy-1.26.4-cp312-cp312-pyodide_2024_0_wasm32.whl pydantic-2.7.0-py3-none-any.whl pydantic_core-2.18.1-cp312-cp312-pyodide_2024_0_wasm32.whl annotated_types-0.6.0-py3-none-any.whl typing_extensions-4.11.0-py3-none-any.whl sqlite3-1.0.0.zip tzdata-2024.1-py2.py3-none-any.whl ssl-1.0.0.zip openssl-1.1.1n.zip"

cd "$ROOT/frontend"
[ -d node_modules ] || npm ci
npx vite build --mode pages

mkdir -p "$ROOT/site/pyodide" "$ROOT/site/wheels"
if [ -z "${PYODIDE_DIR:-}" ]; then
  PYODIDE_DIR="$(mktemp -d)"
  curl -sSL "https://github.com/pyodide/pyodide/releases/download/${PYODIDE_VERSION}/pyodide-${PYODIDE_VERSION}.tar.bz2" | tar -xj -C "$PYODIDE_DIR" --strip-components=1 $(for f in $FILES; do echo "pyodide/$f"; done)
fi
for f in $FILES; do cp "$PYODIDE_DIR/$f" "$ROOT/site/pyodide/"; done

python -m pip download -q --no-deps -d "$ROOT/site/wheels" "fastapi==0.115.6" "starlette==0.41.3" "anyio==4.6.2.post1" "sniffio==1.3.1" "idna==3.10"
(cd "$ROOT/site/wheels" && python -c "import json,glob; json.dump(sorted(glob.glob('*.whl')), open('manifest.json','w'))")

cd "$ROOT/backend"
rm -f "$ROOT/site/backend.zip"
python - "$ROOT/site/backend.zip" <<'PY'
import sys, zipfile
from pathlib import Path
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(Path("app").rglob("*.py")):
        z.write(p)
    for p in sorted(Path("fixtures").glob("*.json")):
        z.write(p)
PY
touch "$ROOT/site/.nojekyll"
echo "완료: $ROOT/site"
