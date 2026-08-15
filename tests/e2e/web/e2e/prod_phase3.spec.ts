import { test, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";
import { readState } from "../helpers/state";

const SNAP_DIR = path.resolve(__dirname, "../../reports/prod-screenshots");
const OUT_DIR = path.resolve(__dirname, "../../reports");
const results: Record<string, any> = {};

function snapshot(page: Page, name: string) {
  fs.mkdirSync(SNAP_DIR, { recursive: true });
  return page.screenshot({ path: path.join(SNAP_DIR, `${name}.png`), fullPage: true });
}

test.describe.configure({ mode: "serial" });

test("Phase3 信号驱动跟单结果前端验证", async ({ browser }) => {
  const state = readState();
  const email = state.real_user_email as string;
  const password = state.real_user_pass as string;
  const user = JSON.parse(fs.readFileSync(path.join(OUT_DIR, "real-user.json"), "utf-8"));

  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (err) => console.log("PAGEERR:", err.message.slice(0, 200)));

  // 登录
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  const modal = page.getByText("风险揭示与免责声明");
  try {
    await modal.waitFor({ state: "visible", timeout: 5000 });
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch { /* no modal */ }
  await page.waitForURL(/\/account/, { timeout: 15000 });

  // E1 我的跟单显示信号驱动的订单/持仓
  await page.goto("/bots", { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);
  const body = await page.locator("body").innerText();
  await snapshot(page, "E1_信号驱动跟单结果");
  results["E1_信号驱动订单持仓显示"] = {
    status: body.includes("持仓数") && body.includes("名义价值") ? "PASS" : "ISSUE",
    findings: [],
    detail: body.slice(0, 500),
  };
  console.log(`[${results["E1_信号驱动订单持仓显示"].status}] E1 信号驱动订单持仓`);

  // E2 奖励/账户概览联动（跟单后账户页）
  await page.goto("/account", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await snapshot(page, "E2_账户概览");
  results["E2_账户页正常"] = { status: (await page.locator("body").innerText()).includes("个人中心") ? "PASS" : "ISSUE", findings: [] };
  console.log(`[${results["E2_账户页正常"].status}] E2 账户页`);

  const counts = Object.values(results).reduce((acc: any, r: any) => { acc[r.status === "PASS" ? "pass" : "issue"]++; return acc; }, { pass: 0, issue: 0 });
  fs.writeFileSync(path.join(OUT_DIR, "prod-phase3.json"), JSON.stringify({ generated_at: new Date().toISOString(), summary: { total: Object.keys(results).length, ...counts }, results }, null, 2), "utf-8");
  console.log(`\n=== Phase3: ${counts.pass} PASS / ${counts.issue} ISSUE ===`);
  await ctx.close();
});
