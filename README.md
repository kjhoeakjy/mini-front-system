# Mini S&T Front Office

금융공학 기반 S&T 프런트 시스템이다.
시장 자료 수집, 옵션 가격 평가, Greeks, 조기상환형 노트(ELS 유사) 설계와 Monte Carlo 평가, 장부 위험 집계, 델타 헤지, 스트레스 테스트를 하나의 흐름으로 연결한다.

- 주문·계좌 연동 기능은 없다. 헤지 거래는 가상 체결로 처리한다.
- 모든 계약은 가상 계약이다. 특정 증권사의 내부 시스템이나 판매 상품을 재현한 것이 아니다.
- 자료 구분(`REAL MARKET DATA`, `CACHED REAL SNAPSHOT`, `MANUAL SCENARIO`, `SYNTHETIC DEMO`)은 화면 상단에 표기된다.

## 화면 구성

| 메뉴 | 내용 |
|---|---|
| ① 시장 데이터 | SPY·QQQ 현물가, 금리, 실현변동성, 상관계수, 배당수익률. 출처·기준일 표기, 수기 입력, 스냅샷 저장 |
| ② 옵션 가격결정 | 유럽형 콜·풋의 BSM 이론가와 Greeks, 충격 손익 비교(Delta / Delta+Gamma / 재평가), 민감도 그래프 |
| ③ 구조화상품 | SPY·QQQ worst-of 스텝다운 노트의 손익구조, 예시 경로, Monte Carlo 이론가·상환 분포·Greeks |
| ④ 포트폴리오 위험 | 포지션별 평가금액과 기초자산별 Delta·Gamma·Vega 합계 |
| ⑤ 델타 헤지 | 델타 중립 가상 거래 수량, 헤지 전후 비교, 재헤지 주기별 시뮬레이션 |
| ⑥ 스트레스 테스트 | 현물·변동성·금리·상관계수 충격의 재평가 손익과 Greeks 근사 비교, 충격 격자 |

기본 장부: SPY 콜 1계약 매도(90일), QQQ 풋 1계약 매수(180일), 스텝다운 노트 10개 매도, 현물 0주.

## 웹 실행 (GitHub Pages)

https://kjhoeakjy.github.io/mini-front-system/

서버 없이 브라우저에서 동작한다. 동일한 Python 계산 코드(`backend/app`)를 Pyodide(WebAssembly)로 실행하며, 화면은 API 호출을 Web Worker 내부의 FastAPI 앱에 전달한다. 최초 접속 시 실행 환경 로딩에 수 초가 소요된다.

- 배포: `main` push 시 `.github/workflows/pages.yml`이 `scripts/build_pages.sh`를 실행해 `site/`를 게시한다.
- 시장 자료: 브라우저에서는 외부 시세 API 호출이 제한되므로 배포 시점에 수집한 원자료(`backend/fixtures/real_raw.json`)를 `CACHED REAL SNAPSHOT`으로 사용한다. 수집 실패 시 가상 자료로 전환한다.
- 저장 내용(스냅샷, 가상 거래)은 브라우저 메모리에 보관되며 새로 고침 시 초기화된다.

## 실행 (Windows)

Python 3.10 이상이 필요하다. `run.bat`을 실행하면 가상환경 생성, 패키지 설치, 서버 실행, 브라우저 열기를 차례로 수행한다.

직접 실행하는 경우:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 연다. 화면은 빌드된 파일(`backend/app/static`)을 백엔드가 제공하므로 Node.js 없이 실행된다.

### 시장 자료

- 시작 시 yfinance(시세)와 FRED(금리)에서 실제 자료를 받는다. 실패하면 저장된 실제 스냅샷, 그다음 가상 자료 순으로 전환하고 화면에 실패 사유를 표시한다.
- FRED API 키는 선택 사항이다. `.env.example`을 `.env`로 복사해 `FRED_API_KEY`를 넣으면 공식 API를 쓰고, 없으면 FRED 공개 CSV 주소를 쓴다.
- 네트워크 없이도 가상 자료(`backend/fixtures/synthetic_demo.json`)로 모든 계산이 동작한다. 가상 자료는 난수로 만든 값이며 실제 시세가 아니다.

### 테스트

```bat
cd backend
python -m pytest
```

브라우저 스모크 테스트(선택, Node.js와 playwright 필요): 서버 실행 후 `node scripts/smoke_e2e.cjs`. Pages 빌드는 `site/`를 정적 서버로 연 뒤 `STATIC=1 BASE_URL=<주소> node scripts/smoke_e2e.cjs`

### 화면 수정 (선택)

```bat
cd frontend
npm install
npm run dev      rem 개발 서버 (API는 8000번 포트로 전달)
npm run build    rem backend/app/static 갱신
```

## 구조

```text
backend/app/quant       계산 모듈 (BSM, 내재변동성, 지급 규칙, Monte Carlo, Greeks, 위험 집계, 헤지, 스트레스)
backend/app/providers   자료 공급자 (yfinance, FRED, 가상 자료)
backend/app/services    스냅샷, 장부, 평가 흐름
backend/app/api         FastAPI 경로 (/api/v1/...)
backend/app/storage     SQLite (스냅샷, 상품, 포지션, 평가 기록, 가상 거래)
backend/tests           단위·API 테스트
frontend/src            React + TypeScript 화면
docs                    모형 가정, 자료 출처, 검증 보고서
```

자료 공급자를 바꾸어도 계산 모듈은 수정하지 않도록 분리했다. 계산 모듈은 API 입력만으로도 동작한다(`POST /api/v1/pricing/european`, `POST /api/v1/structuring/price`). API 목록은 서버 실행 후 http://127.0.0.1:8000/docs 에서 확인한다.

## 구현 범위

| 구분 | 항목 | 상태 |
|---|---|---|
| P0 | 실행 환경, README | 완료 |
| P0 | 가상 스냅샷과 실제 자료 공급자 코드 | 완료 (실제 자료 수집은 개발 환경의 네트워크 제한으로 실행 검증 미완. docs/VALIDATION_REPORT.md 참조) |
| P0 | BSM 가격·Greeks와 테스트 | 완료 |
| P0 | 시장 화면, 옵션 화면 | 완료 |
| P0 | 노트 지급 함수와 경로별 테스트 | 완료 |
| P0 | 2자산 상관 GBM Monte Carlo, 표준오차, 상환 분포 | 완료 |
| P0 | 구조화 화면에서 조건 변경 후 재계산 | 완료 |
| P0 | 가상 장부, 평가금액, 자산별 Delta | 완료 |
| P0 | 델타 헤지 제안·적용, 스트레스 재평가 | 완료 |
| P1 | yfinance 시세·옵션 체인, FRED 금리, 품질 표기 | 코드 완료, 실행 검증 미완 |
| P1 | 내재변동성 역산, 상장 호가와 모형 비교 | 완료 (비교 표는 실제 자료 수집 시 동작) |
| P1 | 노트 Delta·Gamma·Vega·Rho (공통 난수) | 완료 |
| P1 | 스냅샷 저장·불러오기, 평가 기록 | 완료 |
| P1 | 충격 격자, 표본 경로 | 완료 |
| P1 | 단일 유럽형 옵션의 재헤지 시뮬레이션 | 완료 |
| P2 | 미국형 이항모형, 할인곡선, 변동성 스마일, 연속 관측 낙인, 발행 후 노트 재평가 | 미구현 |

노트의 Theta는 제공하지 않는다. 발행 시점 평가만 지원하며, 발행 후 경과한 상품의 재평가에는 낙인·관측 이력이 필요하다.
