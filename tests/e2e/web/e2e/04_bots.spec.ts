import { test, expect } from "@playwright/test";
import { readState } from "../helpers/state";

const PASSWORD = "Test1234!";

/** 04 我的跟单：卡片展示策略名/参数/模拟盘 → 暂停 → 恢复。 */
test("04 我的跟单页面展示机器人并支持暂停/恢复", async ({ page }) => {
  const state = readState();
  const email = state.userA_email as string;
  expect(state.bot_id).toBeTruthy();

  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await page.waitForURL(/\/account/, { timeout: 15000 });

  await page.goto("/bots");
  await expect(page.getByText("E2E测试策略").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/模拟盘|纸面/).first()).toBeVisible({ timeout: 15000 });

  // 暂停
  await page.getByRole("button", { name: "暂停" }).first().click();
  await expect(page.getByText(/已暂停/).first()).toBeVisible({ timeout: 15000 });

  // 恢复
  await page.getByRole("button", { name: "恢复" }).first().click();
  await expect(page.getByText(/已恢复/).first()).toBeVisible({ timeout: 15000 });
});
