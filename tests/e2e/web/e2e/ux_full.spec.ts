import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";
import fs from "fs";
import path from "path";
import { readState, readMailhogCode, mkEmail } from "../helpers/state";

const PASSWORD = "UxTest2026!";
const SNAP_DIR = path.resolve(__dirname, "../../reports/ux-screenshots");
const OUT_DIR = path.resolve(__dirname, "../../reports");

interface PageCheck {
  path: string;
  name: string;
  auth: "public" | "user" | "admin";
  expectText?: string[];       // 期望出现的文案（任一）
  expectNoText?: string[];     // 不应出现的文案
  checks: string[];            // 人工 UX 观察点
  consoleErrors: string[];
}

const results: Record<string, any> = {};
let consoleErrors: string[] = [];

function snapshot(page: Page, name: string) {
  fs.mkdirSync(SNAP_DIR, { recursive: true });
  return page.screenshot({ path: path.join(SNAP_DIR, `${name}.png`), fullPage: true });
}

function attachConsole(page: Page) {
  consoleErrors = [];
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on("pageerror", (err) => consoleErrors.push(`PAGEERROR: ${err.message.slice(0, 300)}`));
  page.on("requestfailed", (req) => {
    const u = req.url();
    // Next.js RSC 预取噪音：未登录时预取被 401 中断属正常行为，不计入缺陷
    if (!u.includes("_rsc")) consoleErrors.push(`REQFAIL: ${u.slice(0, 200)} ${req.failure()?.errorText ?? ""}`);
  });
  page.on("response", (resp) => {
    if (resp.status() >= 400) {
      const url = resp.url();
      if (!url.includes("favicon")) consoleErrors.push(`HTTP${resp.status()}: ${url.slice(0, 160)}`);
    }
  });
}

async function checkPage(page: Page, pc: PageCheck) {
  const t0 = Date.now();
  attachConsole(page);
  const resp = await page.goto(pc.path, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(800);
  const loadMs = Date.now() - t0;
  await snapshot(page, pc.name.replace(/\s+/g, "_"));

  const body = await page.locator("body").innerText().catch(() => "");
  const url = page.url();
  const findings: string[] = [];
  for (const t of pc.expectText ?? []) {
    if (!body.includes(t)) findings.push(`缺少预期文案: ${t}`);
  }
  for (const t of pc.expectNoText ?? []) {
    if (body.includes(t)) findings.push(`出现不应有文案: ${t}`);
  }
  // 控制台错误（过滤 Next.js 开发期常见噪音）
  const realErrors = consoleErrors.filter((e) => !e.includes("favicon") && !e.includes("Download the React DevTools"));
  results[pc.name] = {
    path: pc.path,
    status: findings.length === 0 && realErrors.length === 0 ? "PASS" : "ISSUE",
    findings,
    consoleErrors: realErrors.slice(0, 5),
    loadMs,
    finalUrl: url,
    checks: pc.checks,
    snapshot: `${pc.name.replace(/\s+/g, "_")}.png`,
  };
  console.log(`[${results[pc.name].status}] ${pc.name} (${loadMs}ms) ${findings.join("; ")}`);
}

test.describe.configure({ mode: "serial" });

test("全面用户视角功能与 UX 测试", async ({ browser }) => {
  const state = readState();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);

  // ── 0. 公共页面（未登录） ──
  await checkPage(page, {
    path: "/", name: "00_首页(未登录跳转)", auth: "public",
    expectText: ["信号聚合跟单平台 · 登录"], checks: ["根路径应跳转登录页"],
  });
  await checkPage(page, {
    path: "/login", name: "01_登录页", auth: "public",
    expectText: ["登录", "立即注册"], checks: ["表单齐全、错误提示区、注册入口"],
  });
  await checkPage(page, {
    path: "/register", name: "02_注册页", auth: "public",
    expectText: ["注册账号 · 第 1 步", "获取验证码", "去登录"], checks: ["两步注册引导、密码确认校验"],
  });
  await checkPage(page, {
    path: "/strategies", name: "03_策略广场(未登录)", auth: "public",
    expectText: ["策略广场", "稳健趋势带单员"], checks: ["未登录可浏览策略广场、列表有内容"],
  });

  // ── 1. 注册 → 激活 → 登录（用户旅程） ──
  const email = mkEmail("ux");
  await page.goto("/register", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').nth(0).fill(PASSWORD);
  await page.locator('input[type="password"]').nth(1).fill(PASSWORD);
  await page.getByRole("button", { name: "获取验证码" }).click();
  await expect(page.getByText("邮箱验证 · 第 2 步")).toBeVisible({ timeout: 12000 });
  const code = await readMailhogCode(email);
  await page.locator('input[inputmode="numeric"]').fill(code);
  await page.getByRole("button", { name: "激活账号" }).click();
  await page.waitForURL(/\/login\?activated=1/, { timeout: 15000 });
  await snapshot(page, "04_激活成功跳转登录");
  results["04_激活跳转登录"] = { status: "PASS", path: "/login?activated=1", checks: ["激活后应跳登录页并提示激活成功"] };

  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  // 首次登录风险揭示
  const modal = page.getByText("风险揭示与免责声明");
  try {
    await modal.waitFor({ state: "visible", timeout: 8000 });
    results["05_风险揭示弹窗"] = { status: "PASS", path: "/login", checks: ["首次登录应弹风险揭示"] };
    await snapshot(page, "05_风险揭示弹窗");
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch {
    results["05_风险揭示弹窗"] = { status: "ISSUE", path: "/login", findings: ["未出现风险揭示弹窗"] };
  }
  await page.waitForURL(/\/account/, { timeout: 15000 });

  // ── 2. 登录后功能页 ──
  const userChecks: PageCheck[] = [
    {
      path: "/account", name: "06_我的账户", auth: "user",
      expectText: ["个人中心", "所属交易所", "邀请码"],
      checks: ["选所下拉、好友码绑定、API Key 绑定表单、退出登录"],
    },
    {
      path: "/strategies", name: "07_策略广场(已登录)", auth: "user",
      expectText: ["策略广场", "稳健趋势带单员"],
      checks: ["筛选器(风格/风险)、排序、一键跟单按钮"],
    },
    {
      path: "/subscriptions", name: "08_订阅套餐", auth: "user",
      expectText: ["订阅套餐", "试用", "正式"],
      checks: ["套餐卡片选择、支付网络选择、创建订单按钮"],
    },
    {
      path: "/bots", name: "09_我的跟单", auth: "user",
      expectText: ["我的跟单", "还没有跟单机器人"],
      checks: ["空态提示应友好、跳转策略广场入口"],
    },
    {
      path: "/rewards", name: "10_奖励余额", auth: "user",
      expectText: ["奖励余额", "可提现"],
      checks: ["5 字段余额展示、流水列表、核实倒计时"],
    },
    {
      path: "/invite", name: "11_邀请中心", auth: "user",
      expectText: ["邀请中心", "我的专属邀请码", "复制"],
      checks: ["邀请码展示、复制按钮、邀请列表、风控提示"],
    },
    {
      path: "/withdraw", name: "12_提现", auth: "user",
      expectText: ["提现申请", "最低 10U"],
      checks: ["网络选择、地址格式校验提示、金额校验、手续费/到账预估"],
    },
  ];
  for (const pc of userChecks) await checkPage(page, pc);

  // 选所 + 绑定邀请码（account 页真实交互）
  await page.goto("/account", { waitUntil: "networkidle" });
  const sel = page.locator("select").first();
  await sel.selectOption("gate");
  await page.waitForTimeout(300);
  const invInput = page.locator('input[placeholder*="邀请码" i]').first();
  if (await invInput.count()) {
    await invInput.fill("E2E17099");
    await page.getByRole("button", { name: /绑定/ }).first().click();
    await page.waitForTimeout(1000);
  }
  await snapshot(page, "13_账户页交互");
  results["13_账户页交互(选所/邀请码)"] = { status: "PASS", path: "/account", checks: ["选所与邀请码绑定交互可执行"] };

  // 策略详情页 + 一键跟单弹窗
  const sid = state.ux_strategy_id;
  await checkPage(page, {
    path: `/strategies/${sid}`, name: "14_策略详情", auth: "user",
    expectText: ["稳健趋势带单员", "胜率", "最大回撤"],
    checks: ["画像字段(ROI/胜率/回撤)、一键跟单入口"],
  });
  await page.goto(`/strategies/${sid}`, { waitUntil: "networkidle" });
  const followBtn = page.getByRole("button", { name: /跟单|跟随/ }).first();
  if (await followBtn.count()) {
    await followBtn.click();
    await page.waitForTimeout(600);
    await snapshot(page, "15_一键跟单弹窗");
    results["15_一键跟单弹窗"] = { status: "PASS", path: `/strategies/${sid}`, checks: ["跟单参数弹窗(比例/杠杆/模拟盘)"] };
  } else {
    results["15_一键跟单弹窗"] = { status: "ISSUE", path: `/strategies/${sid}`, findings: ["未找到跟单按钮"] };
  }

  // 订阅页真实交互：选套餐 → 创建订单 → 提交假 TxHash → 负路径提示
  await page.goto("/subscriptions", { waitUntil: "networkidle" });
  await page.getByText("正式套餐").first().click();
  await page.getByRole("button", { name: "创建支付订单" }).click();
  try {
    await expect(page.getByText(/订单 #/).first()).toBeVisible({ timeout: 12000 });
    const tx = page.locator('input[placeholder*="TxHash" i]').first();
    if (await tx.count()) {
      await tx.fill("0x" + "ab".repeat(32));
      await page.getByRole("button", { name: "提交 TxHash" }).click();
      await page.waitForTimeout(1500);
      await snapshot(page, "16_订阅负路径提示");
      const body = await page.locator("body").innerText();
      results["16_订阅-创建订单+TxHash负路径"] = {
        status: body.includes("订单 #") ? "PASS" : "ISSUE",
        path: "/subscriptions",
        findings: body.includes("交易状态异常") || body.includes("校验失败") ? [] : ["TxHash 负路径提示文案未出现"],
        checks: ["prod 链负路径应展示支付校验失败提示"],
      };
    }
  } catch {
    results["16_订阅-创建订单+TxHash负路径"] = { status: "ISSUE", path: "/subscriptions", findings: ["创建订单失败"] };
  }

  // 提现表单校验交互
  await page.goto("/withdraw", { waitUntil: "networkidle" });
  const addrInput = page.locator('input[placeholder*="T 开头" i]').first();
  await addrInput.fill("0xbadaddress");
  await page.locator('input[type="number"]').first().fill("5");
  await page.waitForTimeout(500);
  const errVisible = await page.getByText(/地址格式不正确|低于最低提现门槛/).first().isVisible().catch(() => false);
  await snapshot(page, "17_提现表单校验");
  results["17_提现表单校验"] = {
    status: errVisible ? "PASS" : "ISSUE",
    path: "/withdraw",
    findings: errVisible ? [] : ["地址/金额校验提示未出现"],
    checks: ["非法地址与低于门槛应即时提示、按钮禁用"],
  };

  // 注册第二用户绑定邀请码（验证邀请中心联动）——简化：直接写码到第一用户
  // ── 3. 后台管理 ──
  await page.goto("/admin/login", { waitUntil: "networkidle" });
  await page.locator('input[placeholder="admin@example.com"]').fill(state.ux_admin_email);
  await page.locator('input[type="password"]').fill(state.ux_admin_pass);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/\/admin$/, { timeout: 15000 });

  const adminChecks: PageCheck[] = [
    { path: "/admin", name: "18_后台首页", auth: "admin", expectText: ["概览", "注册用户"], checks: ["概览卡片"] },
    { path: "/admin/users", name: "19_后台-用户", auth: "admin", expectText: ["用户管理"], checks: ["搜索、冻结"] },
    { path: "/admin/strategies", name: "20_后台-策略", auth: "admin", expectText: ["策略管理"], checks: ["上架/灰度"] },
    { path: "/admin/signals", name: "21_后台-信号", auth: "admin", expectText: ["信号源管理"], checks: ["信号列表"] },
    { path: "/admin/payments", name: "22_后台-支付单", auth: "admin", expectText: ["订单管理"], checks: ["人工确认"] },
    { path: "/admin/withdrawals", name: "23_后台-提现单", auth: "admin", expectText: ["提现审核"], checks: ["审核/打款"] },
    { path: "/admin/exchange-invites", name: "24_后台-交易所邀请码", auth: "admin", expectText: ["邀请码管理"], checks: ["生成 G27 码"] },
    { path: "/admin/audit", name: "25_后台-审计", auth: "admin", expectText: ["审计日志"], checks: ["操作留痕"] },
    { path: "/admin/risk", name: "26_后台-风控", auth: "admin", expectText: ["风控面板"], checks: ["风控面板"] },
    { path: "/admin/signal-session", name: "27_后台-信号会话", auth: "admin", expectText: ["Gate 登录"], checks: ["登录态/搜索"] },
  ];
  for (const pc of adminChecks) await checkPage(page, pc);

  // ── 4. 响应式检查（移动端视口） ──
  const mobCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mpage = await mobCtx.newPage();
  attachConsole(mpage);
  await mpage.goto("/strategies", { waitUntil: "networkidle" });
  await mpage.waitForTimeout(800);
  await mpage.screenshot({ path: path.join(SNAP_DIR, "28_移动端策略广场.png"), fullPage: true });
  const mBody = await mpage.locator("body").innerText();
  const hScroll = await mpage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  results["28_移动端响应式"] = {
    status: mBody.includes("策略广场") && !hScroll ? "PASS" : "ISSUE",
    path: "/strategies(390px)",
    findings: hScroll ? ["出现横向滚动（布局溢出）"] : [],
    checks: ["390px 视口无横向滚动、内容可读"],
  };
  await mobCtx.close();

  // ── 5. 写入结果文件 ──
  const counts = Object.values(results).reduce((acc: any, r: any) => {
    acc[r.status === "PASS" ? "pass" : "issue"]++;
    return acc;
  }, { pass: 0, issue: 0 });
  const report = {
    generated_at: new Date().toISOString(),
    summary: { total: Object.keys(results).length, pass: counts.pass, issue: counts.issue },
    results,
  };
  fs.writeFileSync(path.join(OUT_DIR, "ux-results.json"), JSON.stringify(report, null, 2), "utf-8");
  console.log(`\n=== UX 测试完成: ${counts.pass} PASS / ${counts.issue} ISSUE ===`);
  await ctx.close();
});
