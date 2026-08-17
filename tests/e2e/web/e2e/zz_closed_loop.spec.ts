import { test, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";

/* 前端用户角度端到端闭环验证（真实 UI 驱动）
 * 覆盖：登录 → 策略广场(真实数据) → 策略详情 → 开启跟单弹窗(表单字段+风控) → 创建机器人
 *       （含"未绑定 Gate API Key"的引导路径）→ 我的跟单 → 账户 API 绑定弹窗表单交互
 * 说明：真实下单执行依赖交易所真实凭据(生产环境验收项)；本机 dev 用 UI 引导边界验证闭环。
 */
const BASE = "http://localhost:3002";
const API = "http://127.0.0.1:8000";
const EMAIL = "648511672@qq.com";
const PASSWORD = "648511672";
const SNAP_DIR = path.resolve(__dirname, "../../reports/closed-loop-screenshots");

const results: Record<string, any> = {};

function snapshot(page: Page, name: string) {
  fs.mkdirSync(SNAP_DIR, { recursive: true });
  return page.screenshot({ path: path.join(SNAP_DIR, `${name}.png`), fullPage: true });
}

async function apiCall(p: string, method = "GET", body?: unknown, token?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}${p}`, { method, headers, cache: "no-store", body: body ? JSON.stringify(body) : undefined });
  return { status: res.status, body: res.ok ? await res.json() : await res.text() };
}

function record(name: string, status: string, findings: string[] = [], detail = "") {
  results[name] = { status, findings, detail };
  console.log(`[${status}] ${name} ${detail ? "- " + detail : ""}`);
}

test.describe.configure({ mode: "serial" });

test("前端用户角度闭环验证（UI 驱动）", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (err) => console.log("PAGEERR:", err.message.slice(0, 160)));
  const consoleErrors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 160)); });

  // 1. 登录
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  try {
    const modal = page.getByText("风险揭示与免责声明");
    await modal.waitFor({ state: "visible", timeout: 8000 });
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch { /* no modal */ }
  await page.waitForURL(/\/account/, { timeout: 20000 });
  record("S1_用户登录", "PASS", [], `跳转 ${page.url()}`);
  await snapshot(page, "01_登录后账户");

  // 2. 策略广场（真实数据）
  const list = await apiCall("/v1/strategies");
  const items = (list.body as any).items ?? [];
  record("S2_策略广场数据源", list.status === 200 && items.length > 0 ? "PASS" : "ISSUE", items.length ? [] : ["无策略"], `${items.length} 条`);
  await page.goto(`${BASE}/strategies`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await snapshot(page, "02_策略广场");
  const first: any = items[0];

  // 3. 策略详情
  await page.goto(`${BASE}/strategies/${first.id}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const bodyDet = await page.locator("body").innerText();
  const detailOk = bodyDet.includes(first.display_name) && (bodyDet.includes("收益曲线") || bodyDet.includes("实时持仓"));
  record("S3_策略详情页", detailOk ? "PASS" : "ISSUE", detailOk ? [] : ["详情字段缺失"], first.display_name);
  await snapshot(page, "03_策略详情");

  // 4. 开启跟单弹窗（验证弹窗字段：方向/杠杆/保证金/比例/最大名义价值）
  const openBtn = page.locator('button', { hasText: "开启跟单" }).last();
  await openBtn.click();
  await page.waitForTimeout(600);
  const modalText = await page.locator("text=开启跟单").last().isVisible().catch(() => false);
  const modal = await page.locator("body").innerText();
  const fieldsOk =
    ["方向", "杠杆倍数", "保证金模式", "跟单比例", "单笔最大名义价值", "模拟盘"].every((k) => modal.includes(k));
  record("S4_开启跟单弹窗字段", modalText && fieldsOk ? "PASS" : "ISSUE", fieldsOk ? [] : ["弹窗字段缺失"], "");
  await snapshot(page, "04_跟单弹窗");

  // 5. 确认开启跟单 → 前置校验（未绑定 Gate API Key 应给出引导）
  await page.getByRole("button", { name: "确认开启跟单" }).click();
  await page.waitForTimeout(2000);
  const after = await page.locator("body").innerText();
  const msg = after.substring(after.indexOf("API") > -1 ? Math.max(0, after.indexOf("API") - 30) : 0, after.indexOf("API") + 40);
  const guideShown = /请先到「我的账户」绑定任一交易所 API Key/.test(after) || /请先到「我的账户」绑定 Gate API Key/.test(after) || /跟单机器人已创建/.test(after);
  const created = /跟单机器人已创建/.test(after);
  record("S5_创建机器人前置校验", guideShown ? "PASS" : "ISSUE", guideShown ? [] : ["未出现绑定引导或创建成功提示"], created ? "机器人已创建" : msg.trim());
  await snapshot(page, "05_创建结果提示");

  // 6. 账户 → 绑定入口 + 绑定弹窗（验证"登录后如何添加数据源"的引导入口与表单）
  //    注：真实提交会触发 Gate 在线校验并挂起，故本步骤仅验证入口可达 + 弹窗字段呈现，
  //    真实凭据绑定为生产验收项（不在本地 dev 触发网络）。
  await page.goto(`${BASE}/account`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const accBody = await page.locator("body").innerText();
  const entryOk = /接入指引|跟单接入|绑定 API Key|再添加|绑定 Gate API|添加数据源/.test(accBody);

  async function openAndInspectBind(btnSel: string): Promise<{ shown: boolean; fields: boolean }> {
    const btn = page.locator(btnSel).first();
    if (!(await btn.isVisible().catch(() => false))) return { shown: false, fields: false };
    await btn.click();
    await page.waitForTimeout(600);
    const modal = await page.locator("body").innerText();
    const shown = /绑定交易所 API/.test(modal);
    const fields = ["API Key", "API Secret", "提现"].every((k) => modal.includes(k));
    return { shown, fields };
  }

  let s6 = await openAndInspectBind('button:has-text("绑定 API Key")');
  if (!s6.shown) s6 = await openAndInspectBind('button:has-text("再添加")');
  if (!s6.shown) {
    // 兜底：切到「API 密钥管理」Tab
    await page.locator('button:has-text("API 密钥管理")').click();
    await page.waitForTimeout(600);
    s6 = await openAndInspectBind('button:has-text("绑定 API")');
  }
  // 关闭弹窗，避免触发真实交易所网络校验
  try { await page.locator('button:has-text("取消")').first().click(); } catch { /* noop */ }
  await page.waitForTimeout(300);

  record("S6_API绑定入口与表单", entryOk && s6.shown && s6.fields ? "PASS" : "ISSUE",
    entryOk && s6.shown && s6.fields ? [] : entryOk ? (s6.shown ? ["弹窗字段缺失"] : ["绑定弹窗未打开"]) : ["概览页未出现绑定引导入口"],
    `入口=${entryOk} 弹窗=${s6.shown} 字段=${s6.fields}`);
  await snapshot(page, "06_API绑定入口与弹窗");

  // 7. 我的跟单页可达性
  await page.goto(`${BASE}/bots`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const bodyBots = await page.locator("body").innerText();
  record("S7_我的跟单页", /跟单|机器人/.test(bodyBots) ? "PASS" : "ISSUE", /跟单|机器人/.test(bodyBots) ? [] : ["页面内容异常"], "");
  await snapshot(page, "07_我的跟单");

  // 汇总
  const counts = Object.values(results).reduce((acc: any, r: any) => { const k = r.status === "PASS" ? "pass" : r.status === "SKIP" ? "skip" : "issue"; acc[k]++; return acc; }, { pass: 0, issue: 0, skip: 0 });
  fs.writeFileSync(
    path.resolve(__dirname, "../../reports/closed-loop.json"),
    JSON.stringify({ generated_at: new Date().toISOString(), base: BASE, console_errors: consoleErrors, summary: { total: Object.keys(results).length, ...counts }, results }, null, 2), "utf-8"
  );
  console.log(`\n=== 前端闭环: ${counts.pass} PASS / ${counts.issue} ISSUE / ${counts.skip} SKIP ===`);
  console.log("console errors:", consoleErrors.length ? consoleErrors : "none");
  await ctx.close();
});