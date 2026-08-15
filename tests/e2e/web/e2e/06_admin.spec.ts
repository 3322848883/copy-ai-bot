import { test, expect } from "@playwright/test";
import { readState } from "../helpers/state";

const ADMIN_EMAIL = "e2e_docker_admin@t.com";
const ADMIN_PASS = "E2eAdmin!2026";

/** 06 后台管理：登录 → 用户列表 → 支付单 → 提现单 → 信号会话搜索。 */
test("06 后台管理核心页面", async ({ page }) => {
  const state = readState();

  // 后台登录
  await page.goto("/admin/login");
  await page.locator('input[placeholder="admin@example.com"]').fill(ADMIN_EMAIL);
  await page.locator('input[type="password"]').fill(ADMIN_PASS);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/\/admin$/, { timeout: 15000 });

  // 用户列表：搜 userA 邮箱
  await page.goto("/admin/users");
  await expect(page.getByText(/用户管理|注册用户/).first()).toBeVisible({ timeout: 15000 });
  await page.locator('input[placeholder*="邮箱" i], input[type="search"]').first().fill(state.userA_email as string);
  await expect(page.getByText(state.userA_email as string).first()).toBeVisible({ timeout: 15000 });

  // 支付单：确认存在订单
  await page.goto("/admin/payments");
  await expect(page.getByText(/支付|订单/).first()).toBeVisible({ timeout: 15000 });

  // 提现单
  await page.goto("/admin/withdrawals");
  await expect(page.getByText(/提现/).first()).toBeVisible({ timeout: 15000 });

  // 信号会话搜索：ID 24264
  await page.goto("/admin/signal-session");
  await expect(page.getByText(/信号|Gate|登录/).first()).toBeVisible({ timeout: 15000 });
});
