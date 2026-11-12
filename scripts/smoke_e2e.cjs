// 브라우저 스모크 테스트. 서버를 먼저 실행한 뒤 `node scripts/smoke_e2e.cjs` (playwright 필요).
const { chromium } = require("playwright");
const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const SHOT = process.env.SHOT_DIR;
const STATIC = process.env.STATIC === "1"; // Pages 빌드: 서버 API 대조 생략

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const shot = async (n) => SHOT && page.screenshot({ path: `${SHOT}/${n}.png`, fullPage: true });
  const nav = (t) => page.click(`nav.side button:has-text("${t}")`);
  const check = (c, msg) => { if (!c) throw new Error("실패: " + msg); console.log("통과: " + msg); };

  await page.goto(BASE);
  await page.waitForSelector("p.lead", { timeout: 120000 });
  check(await page.locator(".top .badge").first().innerText() === "MANUAL SCENARIO", "기본 모드: 기준 시나리오 표기");
  const kpi = (k) => page.locator(".kpi .v").nth(k).innerText();
  check((await kpi(0)) === "$1,045.06" && (await kpi(2)) === "-$1,045.06", "가격결정: 계약당 이론가 $1,045.06, 매도 평가금액 -$1,045.06");
  await page.waitForSelector(".recharts-line");
  await shot("0-1-pricing");
  await page.click('button:has-text("다음: Greeks")');
  await page.waitForSelector("text=Full Repricing");
  check((await kpi(0)) === "-63.68주", "Greeks: 포지션 Delta -63.68주");
  await shot("0-2-greeks");
  await page.click('button:has-text("다음: 델타 헤지")');
  await page.waitForSelector('button:has-text("가상 헤지 적용")');
  check((await kpi(2)) === "매수 64주", "헤지: SPY 64주 매수 제안");
  await page.click('button:has-text("가상 헤지 적용")');
  await page.waitForSelector("text=추가 거래 없음");
  check((await kpi(0)) === "64주" && (await kpi(1)) === "+0.32주", "헤지 적용 후 현물 64주, 순 Delta +0.32주");
  await shot("0-3-hedge");
  await page.click('button:has-text("다음: 스트레스 테스트")');
  await page.waitForSelector("text=합산 평가손익");
  const lead = await page.locator("p.lead").innerText();
  check(lead.includes("−$340.73") && lead.includes("현물 64주") && !lead.includes("$0.00"), "스트레스: 헤지 전후 재평가 손익 표시 (" + lead.slice(0, 60) + ")");
  await shot("0-4-stress");
  await page.click('button:has-text("다음: 구조화")');
  await page.waitForSelector("text=발행가 일치 참여율");
  check((await kpi(0)) === "$1,003.48", "구조화: 원금지급형 채권 이론가 $1,003.48");
  await shot("0-5-note");

  await page.click('.top .seg button:has-text("고급")');
  check(await page.locator(".top .badge").first().innerText() !== "", "상단에 자료 표기가 보임");
  await page.waitForSelector("text=SPY 현물가");
  await shot("1-market");

  await nav("옵션 가격결정");
  await page.waitForSelector('h2:has-text("포지션 Greeks")');
  const api = STATIC ? null : await (await page.request.post(BASE + "/api/v1/risk/portfolio", { data: { n_paths: 20000, seed: 42 } })).json();
  const p0 = await page.locator(".kpi .v").first().innerText();
  await page.click('button:has-text("현물가 +5%")');
  await page.waitForFunction((old) => { const e = document.querySelector(".kpi .v"); return e && e.textContent !== old; }, p0);
  check((await page.locator(".kpi .v").first().innerText()) !== p0, "현물가를 바꾸면 옵션 이론가가 다시 계산됨");
  await shot("2-option");

  await nav("구조화상품");
  await page.waitForSelector('h2:has-text("예시 경로별 상환금액")');
  await page.click('button:has-text("Monte Carlo 평가")');
  await page.waitForSelector('h2:has-text("상환 유형별 경로 비율")', { timeout: 60000 });
  await shot("3-structuring");

  await nav("포트폴리오 위험");
  await page.waitForSelector('h2:has-text("포지션별 평가금액")', { timeout: 60000 });
  const shown = await page.locator(".kpi .v").first().innerText();
  const want = STATIC ? "" : (api.totals.mtm < 0 ? "-$" : "+$") + Math.abs(api.totals.mtm).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!STATIC) check(shown === want, `장부 평가금액이 API 직접 호출 결과와 일치 (${shown})`);
  await shot("4-portfolio");

  await nav("델타 헤지");
  await page.waitForSelector('h2:has-text("델타 헤지 제안")', { timeout: 60000 });
  await page.click('button:has-text("가상 헤지 적용")');
  await page.waitForSelector('h2:has-text("가상 거래 내역")', { timeout: 60000 });
  await page.click('button:has-text("최근 6개월 실행")');
  await page.waitForSelector('th:has-text("재헤지 주기")', { timeout: 60000 });
  await shot("5-hedge");

  await nav("스트레스 테스트");
  await page.waitForSelector('h2:has-text("기본 시나리오")', { timeout: 60000 });
  await page.click('.card:has-text("현물 충격별") button:has-text("산출")');
  await page.waitForSelector("table.heat", { timeout: 60000 });
  await shot("6-stress");

  check(errors.length === 0, "브라우저 오류 없음 " + JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
