// 브라우저 스모크 테스트. 서버를 먼저 실행한 뒤 `node scripts/smoke_e2e.cjs` (playwright 필요).
const { chromium } = require("playwright");
const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const SHOT = process.env.SHOT_DIR;

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
  await page.waitForSelector("text=DATA MODE");
  check(await page.locator(".top .badge").first().innerText() !== "", "상단에 자료 표기가 보임");
  await page.waitForSelector("text=SPY 현물가");
  await shot("1-market");

  await nav("옵션");
  await page.waitForSelector('h2:has-text("포지션 Greeks")');
  const api = await (await page.request.post(BASE + "/api/v1/risk/portfolio", { data: { n_paths: 20000, seed: 42 } })).json();
  const p0 = await page.locator(".kpi .v").first().innerText();
  await page.click('button:has-text("현물가 +5%")');
  await page.waitForFunction((old) => { const e = document.querySelector(".kpi .v"); return e && e.textContent !== old; }, p0);
  check((await page.locator(".kpi .v").first().innerText()) !== p0, "현물가를 바꾸면 옵션 이론가가 다시 계산됨");
  await shot("2-option");

  await nav("구조화");
  await page.waitForSelector('h2:has-text("예시 경로 4개")');
  await page.click('button:has-text("Monte Carlo 평가 실행")');
  await page.waitForSelector('h2:has-text("상환 유형별 경로 비율")', { timeout: 60000 });
  await shot("3-structuring");

  await nav("장부");
  await page.waitForSelector('h2:has-text("포지션별 평가와 위험")', { timeout: 60000 });
  const shown = await page.locator(".kpi .v").first().innerText();
  const want = (api.totals.mtm < 0 ? "-$" : "+$") + Math.abs(api.totals.mtm).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  check(shown === want, `장부 평가금액이 API 직접 호출 결과와 일치 (${shown})`);
  await shot("4-portfolio");

  await nav("헤지");
  await page.waitForSelector('h2:has-text("델타 헤지 제안")', { timeout: 60000 });
  await page.click('button:has-text("가상 헤지 적용")');
  await page.waitForSelector('h2:has-text("가상 거래 기록")', { timeout: 60000 });
  await page.click('button:has-text("최근 약 6개월")');
  await page.waitForSelector('th:has-text("재헤지 주기")', { timeout: 60000 });
  await shot("5-hedge");

  await nav("스트레스");
  await page.waitForSelector('h2:has-text("기본 시나리오")', { timeout: 60000 });
  await page.click('.card:has-text("충격 조합별") button:has-text("계산")');
  await page.waitForSelector("table.heat", { timeout: 60000 });
  await shot("6-stress");

  check(errors.length === 0, "브라우저 오류 없음 " + JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
