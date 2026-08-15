import { test, expect } from "@playwright/test";
import { readState } from "../helpers/state";

const PASSWORD = "Test1234!";

/** 03 订阅页：登录 → 创建正式套餐订单 → 提交假 TxHash → prod 链负路径展示「支付校验失败」。 */
test("03 订阅页创建订单并提交 TxHash（负路径展示）", async ({ page }) => {
  const state = readState();
  const email = state.userA_email as string;

  // 直接注入 token 跳过登录页（API 阶段已有 token；此处重新登录以走 UI 流程）
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /登\s*录/ }).click();
  // 该用户已在 API 阶段接受风险揭示 → 直接进 account
  await page.waitForURL(/\/account/, { timeout: 15000 });

  await page.goto("/subscriptions");
  await expect(page.getByText("正式套餐").first()).toBeVisible({ timeout: 15000 });

  // 选择正式套餐（价格 19.9）——点击套餐卡片
  await page.getByText("19.9", { exact: false }).first().click();

  // 创建支付订单
  await page.getByRole("button", { name: "创建支付订单" }).click();
  await expect(page.getByText(/订单 #/).first()).toBeVisible({ timeout: 15000 });

  // 提交假 TxHash → prod 链负路径 → 校验失败文案
  await page.locator('input[placeholder*="TxHash" i]').first().fill("0x" + "ab".repeat(32));
  await page.getByRole("button", { name: "提交 TxHash" }).click();
  await expect(page.getByText(/支付校验失败|交易状态异常/).first()).toBeVisible({ timeout: 20000 });
});
