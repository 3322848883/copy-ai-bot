import { test, expect, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";
import { readState, readMailhogCode, mkEmail } from "../helpers/state";

const PASSWORD = "RealProd2026!";
const SNAP_DIR = path.resolve(__dirname, "../../reports/prod-screenshots");
const OUT_DIR = path.resolve(__dirname, "../../reports");
const results: Record<string, any> = {};

function snapshot(page: Page, name: string) {
  fs.mkdirSync(SNAP_DIR, { recursive: true });
  return page.screenshot({ path: path.join(SNAP_DIR, `${name}.png`), fullPage: true });
}

test.describe.configure({ mode: "serial" });

test("Phase1 真实信号源前端显示 + 用户注册", async ({ browser }) => {
  const state = readState();
  const strategies = state.real_strategies as Array<{ strategy_id: number; name: string; trader_external: string }>;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (err) => console.log("PAGEERR:", err.message.slice(0, 200)));

  // A1 策略广场显示真实信号源
  await page.goto("/strategies", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const bodyA = await page.locator("body").innerText();
  const names = strategies.map((s) => s.name);
  const missing = names.filter((n) => !bodyA.includes(n));
  results["A1_策略广场显示真实信号源"] = {
    status: missing.length === 0 ? "PASS" : "ISSUE",
    findings: missing.length ? [`未显示: ${missing.join(",")}`] : [],
    detail: `期望 ${names.join("/")} 全部显示`,
  };
  await snapshot(page, "A1_策略广场真实信号源");
  console.log(`[${results["A1_策略广场显示真实信号源"].status}] A1 策略广场`);

  // A2 策略详情真实画像
  const sid = strategies[0].strategy_id;
  await page.goto(`/strategies/${sid}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const bodyD = await page.locator("body").innerText();
  results["A2_策略详情真实画像"] = {
    status: bodyD.includes(names[0]) && (bodyD.includes("胜率") || bodyD.includes("收益") || bodyD.includes("回撤")) ? "PASS" : "ISSUE",
    findings: [],
  };
  await snapshot(page, "A2_策略详情真实画像");
  console.log(`[${results["A2_策略详情真实画像"].status}] A2 策略详情`);

  // A3 注册新用户
  const email = mkEmail("prod");
  await page.goto("/register", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').nth(0).fill(PASSWORD);
  await page.locator('input[type="password"]').nth(1).fill(PASSWORD);
  await page.getByRole("button", { name: "获取验证码" }).click();
  await expect(page.getByText("邮箱验证 · 第 2 步")).toBeVisible({ timeout: 15000 });
  const code = await readMailhogCode(email);
  await page.locator('input[inputmode="numeric"]').fill(code);
  await page.getByRole("button", { name: "激活账号" }).click();
  await page.waitForURL(/\/login\?activated=1/, { timeout: 15000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  const modal = page.getByText("风险揭示与免责声明");
  try {
    await modal.waitFor({ state: "visible", timeout: 8000 });
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch { /* no modal */ }
  await page.waitForURL(/\/account/, { timeout: 15000 });
  results["A3_注册激活登录"] = { status: "PASS", path: "/account" };
  await snapshot(page, "A3_注册激活登录");
  console.log("[PASS] A3 注册激活登录");

  // 写入用户 state（供 stage B 数据准备与后续 phase）
  fs.writeFileSync(
    path.join(OUT_DIR, "real-user.json"),
    JSON.stringify({ email, password: PASSWORD, strategy_id: sid, strategy_name: names[0], all_strategies: names }, null, 2),
    "utf-8"
  );
  const statePath = path.resolve(__dirname, "../../state.json");
  const cur = JSON.parse(fs.readFileSync(statePath, "utf-8"));
  cur.real_user_email = email;
  cur.real_user_pass = PASSWORD;
  fs.writeFileSync(statePath, JSON.stringify(cur, null, 2), "utf-8");
  console.log("[INFO] real user saved:", email);

  // A4 订阅页展示
  await page.goto("/subscriptions", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const bodyS = await page.locator("body").innerText();
  results["A4_订阅页展示"] = { status: bodyS.includes("试用") || bodyS.includes("正式") ? "PASS" : "ISSUE", findings: [] };
  await snapshot(page, "A4_订阅页");
  console.log(`[${results["A4_订阅页展示"].status}] A4 订阅页`);

  // 汇总
  const counts = Object.values(results).reduce((acc: any, r: any) => { acc[r.status === "PASS" ? "pass" : "issue"]++; return acc; }, { pass: 0, issue: 0 });
  fs.writeFileSync(path.join(OUT_DIR, "prod-phase1.json"), JSON.stringify({ generated_at: new Date().toISOString(), summary: { total: Object.keys(results).length, ...counts }, results }, null, 2), "utf-8");
  console.log(`\n=== Phase1: ${counts.pass} PASS / ${counts.issue} ISSUE ===`);
  await ctx.close();
});
