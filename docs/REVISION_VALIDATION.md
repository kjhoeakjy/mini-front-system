# 개정 검증: 단일 거래 흐름과 원금지급형 채권

검증일 2026-11-12. 환경: Python 3.13, numpy 2.5 (Linux), Chromium(Playwright).

## 변경 파일

| 구분 | 파일 | 내용 |
|---|---|---|
| 신규 | `backend/app/quant/principal_protected_note.py` | 지급액, 할인채 + 콜 분석식 가격, Greeks, 발행가 일치 참여율, 1자산 Monte Carlo 대조 |
| 신규 | `backend/app/api/simple_structuring.py` | `POST /api/v1/simple-structuring/price` |
| 신규 | `backend/app/api/deal.py` | `POST /api/v1/deal/start` (기준 시나리오 또는 시장 데이터로 단일 거래 생성) |
| 수정 | `backend/app/services/book_service.py` | 장부 분리(`DEMO`, `DEAL`), 장부 단위 초기화, 거래 시점 행사가·프리미엄 기록 |
| 수정 | `backend/app/api/portfolio.py`, `hedge.py`, `stress.py` | `book` 인자 추가. 생략 시 기존 동작 유지 |
| 수정 | `backend/app/storage/database.py` | 가상 거래 내역에 장부 열 추가(기존 DB 자동 이행) |
| 수정 | `backend/app/services/snapshot_service.py` | 기준 시나리오 스냅샷을 기본 스냅샷 조회와 목록에서 제외 |
| 신규 | `frontend/src/pages/GuidedDesk.tsx`, `components/DealSummary.tsx` | 기본 모드 5단계 화면 |
| 수정 | `frontend/src/App.tsx` | 기본·고급 모드 전환, 단일 거래 상태 공유 |
| 수정 | `frontend/src/pages/OptionLab.tsx`, `Structuring.tsx`, `Portfolio.tsx` | 만기 payoff 표기, worst-of 경로 표기, MTM 표기 |
| 무수정 | `black_scholes.py`, `monte_carlo.py`, `autocallable_payoff.py`, `numerical_greeks.py`, `hedging.py`, `stress.py`(quant) | 계산 로직 변경 없음 |

## 실행 결과

| 명령 | 결과 |
|---|---|
| `cd backend && python -m pytest -q` | 131건 통과 (기존 123건 + 신규 8건) |
| `cd frontend && npx tsc --noEmit && npm run build` | 성공 |
| `node scripts/smoke_e2e.cjs` (FastAPI 서버) | 12개 확인 항목 통과, 브라우저 오류 없음 |
| `bash scripts/build_pages.sh` 후 `STATIC=1 node scripts/smoke_e2e.cjs` (Pyodide 정적 빌드) | 11개 확인 항목 통과(서버 API 대조 1건 제외), 브라우저 오류 없음 |

## 기준 시나리오 기준값 (S = K = 100, T = 1, r = 5%, q = 0, σ = 20%)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 콜 주당 이론가 | 10.4505835722 | `test_base_case_reference_values` |
| 매도 1계약 평가금액 | −1,045.05835722 | 동일, `/risk/portfolio` (book=DEAL) |
| 포지션 Delta | −63.68306512주 | 동일 |
| 포지션 Gamma / Vega | −1.8762 / −$37.52 | 동일 |
| 정수 주식 헤지 제안 | SPY +64주, 적용 후 순 Delta +0.3169주 | `test_deal_flow_price_hedge_stress` |
| 재제안 | 추가 거래 0주 | 동일 |
| SPY +5% 재평가 손익 | 헤지 전 −$340.73, 헤지 후 −$20.73 | 동일, 화면 스모크 |
| 변동성 +5%p | 매도 포지션 평가손익 음수 | 동일 |
| 행사가 유지 | 현물가 변경 스냅샷에서도 K = 100, 체결 프리미엄 유지 | `test_deal_keeps_strike_when_market_changes` |
| 장부 분리 | 단일 거래 생성·헤지·초기화 전후 고급 장부 포지션·거래 내역 동일 | `test_deal_flow_price_hedge_stress` |

## 원금지급형 채권 (N = 1,000, α = 0.5, S0 = 100)

| 항목 | 결과 |
|---|---|
| 만기 SPY 80 / 100 / 120 지급액 | 1,000 / 1,000 / 1,100 |
| 이론가 | 1,003.48 = 할인채 951.23 + 콜옵션 52.25 |
| α = 0 | 이론가 = 할인채 가치 |
| α 증가 | 이론가 비감소 |
| Delta·Gamma·Vega | 콜 Greeks × α·N/S0와 일치. Delta·Rho·Theta는 중앙차분과 일치(상대오차 1e-6) |
| 발행가 일치 참여율 | 역산 참여율 대입 시 이론가 1,000 |
| Monte Carlo 대조 | 200,000 경로에서 분석식과 표준오차 3배 이내, 동일 시드 재현 |
| 참여율 입력 오류 | 50(=5,000%) 입력 시 422 |

## 미검증·한계

- 실제 시장 데이터 수집(yfinance, FRED): 검증 환경에서 외부 접속이 차단되어 미검증. 실패 시 전환 경로와 배포 시점 수집분 사용 경로는 확인함.
- GitHub Pages 실제 주소: 검증 환경에서 접속 불가. 동일 정적 빌드를 로컬 서버에서 확인함.
- 현금계정 미구현: 프리미엄, 헤지 대금, 거래 비용을 합산한 누적 손익은 제공하지 않음. 화면의 손익은 평가금액 변화임.
- 원금지급형 채권은 평가 전용이며 장부 편입을 제공하지 않음.
- 체결가는 이론가 체결 가정. 호가 스프레드, 유동성, 조달 비용, 발행사 신용위험 미반영.
