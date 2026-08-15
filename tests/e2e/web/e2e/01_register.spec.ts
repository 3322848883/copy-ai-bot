import { test, expect } from "@playwright/test";
import { mkEmail, readMailhogCode } from "../helpers/state";

const PASSWORD = "Test1234!";

/** 注册 → 邮箱验证 → 登录，完整走 /register 与 /login 页面。 */
test("01 注册激活 → 登录全流程", async ({ page }) => {
  const email = mkEmail("web");

  await page.goto("/register");
  await expect(page.getByText("注册账号 · 第 1 步")).toBeVisible();

  // 第 1 步：填写邮箱密码
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').nth(0).fill(PASSWORD);
  await page.locator('input[type="password"]').nth(1).fill(PASSWORD);
  await page.getByRole("button", { name: "获取验证码" }).click();
  await expect(page.getByText("邮箱验证 · 第 2 步")).toBeVisible({ timeout: 10000 });

  // 第 2 步：从 mailhog 读验证码
  const code = await readMailhogCode(email);
  await page.locator('input[inputmode="numeric"]').fill(code);
  await page.getByRole("button", { name: "激活账号" }).click();

  // 跳转登录页（activated=1）
  await page.waitForURL(/\/login\?activated=1/, { timeout: 15000 });
  await expect(page.getByText("信号聚合跟单平台 · 登录")).toBeVisible();

  // 登录
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();

  // 首次登录触发风险揭示弹窗（幂等：已确认则跳过）
  const modal = page.getByText("风险揭示与免责声明");
  try {
    await modal.waitFor({ state: "visible", timeout: 8000 });
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch {
    /* 弹窗未出现，继续 */
  }
  await page.waitForURL(/\/account/, { timeout: 15000 });
});
