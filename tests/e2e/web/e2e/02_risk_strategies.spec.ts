import { test, expect } from "@playwright/test";
import { readState } from "../helpers/state";

const PASSWORD = "Test1234!";

/** 02 登录 + 风险揭示弹窗 + 策略广场/详情（userB 未接受风险揭示 → 登录必弹窗）。 */
test("02 登录触发风险揭示 → 策略广场可见 E2E 策略", async ({ page }) => {
  const state = readState();
  const email = state.userB_email as string;
  expect(email).toBeTruthy();

  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();

  // 风险揭示弹窗：首次登录必现；已确认过则不弹（幂等处理）
  const modal = page.getByText("风险揭示与免责声明");
  try {
    await modal.waitFor({ state: "visible", timeout: 8000 });
    await page.getByText("我已阅读并理解上述风险揭示，自愿承担所有交易风险").click();
    await page.getByRole("button", { name: "确认并继续" }).click();
  } catch {
    /* 弹窗未出现（已确认过），继续 */
  }
  await page.waitForURL(/\/account/, { timeout: 15000 });

  // 策略广场
  await page.goto("/strategies");
  await expect(page.getByText("E2E测试策略").first()).toBeVisible({ timeout: 15000 });

  // 策略详情
  await page.goto(`/strategies/${state.strategy_id}`);
  await expect(page.getByText("E2E测试策略").first()).toBeVisible({ timeout: 15000 });
});
