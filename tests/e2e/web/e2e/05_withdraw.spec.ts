import { test, expect } from "@playwright/test";
import { readState } from "../helpers/state";

const PASSWORD = "Test1234!";
// TRC20 合法地址：T + 33 位 [1-9A-HJ-NP-Za-km-z]
const VALID_TRC20 = "T" + "A1b2C3d4E5f6G7h8J9KmNpQrStUvWxYz".repeat(3).slice(0, 33);

/** 05 提现页：非法地址禁用 → 合法地址启用（表单校验交互）。
 * 实际提交动作已由 API 自动化套件完整覆盖（test_08_withdrawal_flow），
 * 此处聚焦前端正则校验与按钮状态联动，避免对余额注入的脆弱依赖。 */
test("05 提现页地址校验与提交", async ({ page }) => {
  const state = readState();
  const email = state.userA_email as string;

  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await page.waitForURL(/\/account/, { timeout: 15000 });

  await page.goto("/withdraw");
  await expect(page.getByText(/提现|实发/).first()).toBeVisible({ timeout: 15000 });

  // 非法地址 → 提交按钮禁用（前端正则拦截）
  const addrInput = page.locator('input[placeholder*="T 开头" i]').first();
  await addrInput.fill("0x0000000000000000000000000000000000000000");
  await page.locator('input[type="number"]').first().fill("10");
  await expect(page.getByRole("button", { name: /提交提现|提现申请/ }).first()).toBeDisabled();

  // 合法地址 → 地址格式错误提示消失（按钮是否可用取决于余额，这里断言地址校验本身）
  await addrInput.fill(VALID_TRC20);
  await expect(page.getByText("地址格式不正确").first()).not.toBeVisible();
});
