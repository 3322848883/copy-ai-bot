// 登录页 UI 验证：品牌面板 + 两步认证 + TOTP 浏览器流程（含 confirm 激活）
import { chromium } from "playwright";
import { execSync } from "node:child_process";

const BASE = "http://127.0.0.1:3001";
const API = "http://127.0.0.1:8000";
const EMAIL = "648511672@qq.com";
const PWD = "648511672";
const PY = "C:\\Users\\w6485\\Desktop\\AI 量化\\信号聚合AI\\.venv\\Scripts\\python.exe";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console.error: ${m.text()}`); });

// 0. API 启用 TOTP（setup + confirm）
const loginRes = await fetch(`${API}/admin/v1/auth/login`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: EMAIL, password: PWD }),
});
const login = await loginRes.json();
const h = { "Content-Type": "application/json", Authorization: `Bearer ${login.access_token}` };
const setupRes = await fetch(`${API}/admin/v1/auth/totp/setup`, { method: "POST", headers: h });
const setup = await setupRes.json();
const secret = setup.secret;
const code0 = execSync(`${PY} -c "import pyotp; print(pyotp.TOTP('${secret}').now())"`).toString().trim();
const confirmRes = await fetch(`${API}/admin/v1/auth/totp/confirm`, { method: "POST", headers: h, body: JSON.stringify({ code: code0 }) });
console.log("TOTP 激活:", confirmRes.status, JSON.stringify(await confirmRes.json()));

// 1. 打开登录页
await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
const loginText = await page.locator("body").innerText();
console.log("品牌面板 运营管理后台 =", loginText.includes("运营管理后台"));
console.log("ADMIN CONSOLE =", loginText.includes("ADMIN CONSOLE"));
console.log("安全登录按钮 =", loginText.includes("安全登录"));
console.log("登录行为将被记录 =", loginText.includes("登录行为将被记录"));
console.log("独立 JWT audience =", loginText.includes("独立 JWT audience"));
await page.screenshot({ path: "c:\\Users\\w6485\\.trae-cn\\work\\6a7b36fe0e1d7d97af5616c4\\login_step1.png" });

// 2. 错误密码 → 错误提示（剩余次数）
await page.locator(".view.active .input").first().fill(EMAIL);
await page.locator('.view.active input[type="password"]').fill("wrong-pass-123");
await page.locator(".view.active .btn-admin").click();
await page.waitForTimeout(2000);
const errText = await page.locator("body").innerText();
console.log("错误提示 剩余4次 =", errText.includes("剩余"));
await page.screenshot({ path: "c:\\Users\\w6485\\.trae-cn\\work\\6a7b36fe0e1d7d97af5616c4\\login_err.png" });

// 3. 正确密码 → 进入步骤2 TOTP
await page.locator('.view.active input[type="password"]').fill(PWD);
await page.locator(".view.active .btn-admin").click();
await page.waitForTimeout(2500);
const step2Text = await page.locator("body").innerText();
console.log("步骤2 双因素验证 =", step2Text.includes("双因素验证"));
console.log("OTP 输入框数量 =", await page.locator(".otp-cell").count());
console.log("验证并登录按钮 =", step2Text.includes("验证并登录"));
console.log("倒计时显示 =", /剩余 \d+ 秒/.test(step2Text));
await page.screenshot({ path: "c:\\Users\\w6485\\.trae-cn\\work\\6a7b36fe0e1d7d97af5616c4\\login_step2.png" });

// 4. 输入动态码 → 进入后台
const code = execSync(`${PY} -c "import pyotp; print(pyotp.TOTP('${secret}').now())"`).toString().trim();
console.log("动态码:", code);
for (let i = 0; i < 6; i++) {
  await page.locator(".otp-cell").nth(i).fill(code[i]);
  await page.waitForTimeout(100);
}
await page.waitForTimeout(3000);
const finalUrl = page.url();
console.log("验证后 URL =", finalUrl);
console.log("进入后台 =", finalUrl === `${BASE}/` || finalUrl === `${BASE}`);
const homeText = await page.locator("body").innerText();
console.log("后台首页 数据概览 =", homeText.includes("数据概览"));
await page.screenshot({ path: "c:\\Users\\w6485\\.trae-cn\\work\\6a7b36fe0e1d7d97af5616c4\\login_done.png" });

// 5. 清理：停用 TOTP
const code2 = execSync(`${PY} -c "import pyotp; print(pyotp.TOTP('${secret}').now())"`).toString().trim();
const disResp = await fetch(`${API}/admin/v1/auth/totp/disable`, {
  method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${login.access_token}` },
  body: JSON.stringify({ code: code2 }),
});
console.log("停用 TOTP:", disResp.status);

console.log("JS errors:", errors.length ? errors.slice(0, 5) : "none");
await browser.close();
