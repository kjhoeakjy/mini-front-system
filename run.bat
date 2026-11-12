@echo off
rem Windows 실행 스크립트. 처음 실행 시 가상환경을 만들고 필요한 패키지를 설치한다.
cd /d %~dp0backend
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --port 8000
