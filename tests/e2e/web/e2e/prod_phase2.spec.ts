import { test, expect, type Page } from "@playwright/test";
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

test("Phase2 一键跟单创建 bot + 我的跟单", async ({ browser }) => {
  const state = readState();
  const email = state.real_user_email as string;
  const password = state.real_user_pass as string;
  const user = JSON.parse(fs.readFileSync(path.join(OUT_DIR, "real-user.json"), "utf-8"));
  const sid = user.strategy_id;
  const name = user.strategy_name;
  expect(email && password).toBeTruthy();

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

  // B 订阅状态（stage B 外部已激活）
  await page.goto("/subscriptions", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const bodySub = await page.locator("body").innerText();
  results["B_订阅已激活"] = { status: bodySub.includes("订阅有效") || bodySub.includes("正式") || bodySub.includes("试用") ? "PASS" : "ISSUE", findings: bodySub.includes("未订阅") ? ["订阅未激活（stage B 未执行）"] : [] };
  await snapshot(page, "B_订阅状态");
  console.log(`[${results["B_订阅已激活"].status}] B 订阅状态`);

  // C1 策略详情一键跟单
  await page.goto(`/strategies/${sid}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const followBtn = page.getByRole("button", { name: /开始跟单/ }).first();
  if (await followBtn.count()) {
    await followBtn.click();
    await page.waitForTimeout(600);
    await snapshot(page, "C1_一键跟单弹窗");
    const numInputs = page.locator('input[type="number"]');
    await numInputs.nth(0).fill("20");
    await numInputs.nth(1).fill("10");
    const paperCb = page.locator('input[type="checkbox"]').first();
    if (await paperCb.count()) await paperCb.check();
    await page.getByRole("button", { name: /确认跟单/ }).click();
    await page.waitForTimeout(2500);
    const bodyC = await page.locator("body").innerText();
    results["C1_一键跟单创建bot"] = {
      status: bodyC.includes("跟单机器人已创建") || bodyC.includes("我的跟单") ? "PASS" : "ISSUE",
      findings: bodyC.includes("请先到") ? ["提示需要绑定 API Key（stage B 应已直插）"] : bodyC.includes("无有效订阅") ? ["无有效订阅"] : [],
      detail: bodyC.slice(0, 300),
    };
    await snapshot(page, "C1_跟单创建结果");
  } else {
    results["C1_一键跟单创建bot"] = { status: "ISSUE", findings: ["未找到开始跟单按钮"] };
  }
  console.log(`[${results["C1_一键跟单创建bot"].status}] C1 一键跟单`);

  // C2 我的跟单显示机器人
  await page.goto("/bots", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const bodyB = await page.locator("body").innerText();
  results["C2_我的跟单显示机器人"] = {
    status: bodyB.includes(name) && bodyB.includes("模拟盘") ? "PASS" : "ISSUE",
    findings: !bodyB.includes(name) ? ["机器人未显示"] : !bodyB.includes("模拟盘") ? ["模拟盘徽标缺失"] : [],
    detail: bodyB.slice(0, 300),
  };
  await snapshot(page, "C2_我的跟单机器人");
  console.log(`[${results["C2_我的跟单显示机器人"].status}] C2 我的跟单 ${name}`);

  // C3 暂停/恢复
  const pauseBtn = page.getByRole("button", { name: "暂停" }).first();
  if (await pauseBtn.count()) {
    await pauseBtn.click();
    await page.waitForTimeout(1200);
    const bodyP = await page.locator("body").innerText();
    results["C3_跟单暂停恢复"] = { status: bodyP.includes("已暂停") ? "PASS" : "ISSUE", findings: [] };
    const resumeBtn = page.getByRole("button", { name: "恢复" }).first();
    if (await resumeBtn.count()) {
      await resumeBtn.click();
      await page.waitForTimeout(1200);
      const bodyR = await page.locator("body").innerText();
      if (bodyR.includes("已恢复") === false) results["C3_跟单暂停恢复"].findings.push("恢复后未显示已恢复");
    }
    await snapshot(page, "C3_暂停恢复结果");
  } else {
    results["C3_跟单暂停恢复"] = { status: "ISSUE", findings: ["无暂停按钮"] };
  }
  console.log(`[${results["C3_跟单暂停恢复"].status}] C3 暂停/恢复`);

  const counts = Object.values(results).reduce((acc: any, r: any) => { acc[r.status === "PASS" ? "pass" : "issue"]++; return acc; }, { pass: 0, issue: 0 });
  fs.writeFileSync(path.join(OUT_DIR, "prod-phase2.json"), JSON.stringify({ generated_at: new Date().toISOString(), summary: { total: Object.keys(results).length, ...counts }, results }, null, 2), "utf-8");
  console.log(`\n=== Phase2: ${counts.pass} PASS / ${counts.issue} ISSUE ===`);
  await ctx.close();
});
