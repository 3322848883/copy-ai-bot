"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { tokenStore } from "@/lib/api";

const MENU = [
  { href: "/admin", label: "概览", icon: "▦" },
  { href: "/admin/users", label: "用户管理", icon: "👤" },
  { href: "/admin/review", label: "主号审核", icon: "🔍" },
  { href: "/admin/exchange-invites", label: "邀请码管理", icon: "🔑" },
  { href: "/admin/strategies", label: "策略管理", icon: "📈" },
  { href: "/admin/orders", label: "跟单订单", icon: "🧾" },
  { href: "/admin/invites", label: "邀请奖励", icon: "🎁" },
  { href: "/admin/wallets", label: "钱包账本", icon: "💳" },
  { href: "/admin/withdrawals", label: "提现审核", icon: "💰" },
  { href: "/admin/payments", label: "订单管理", icon: "📦" },
  { href: "/admin/audit", label: "审计日志", icon: "🛡" },
  { href: "/admin/risk", label: "风控面板", icon: "⚠" },
  { href: "/admin/signal-session", label: "信号源登录", icon: "🔐" },
];

/** M5 T5.9 后台布局：侧边栏 + 内容区（aud=admin 独立会话）。 */
export default function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/admin/login") return <>{children}</>;

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0b1220" }}>
      <aside style={{ width: 200, borderRight: "1px solid var(--rule)", padding: "20px 12px", flexShrink: 0 }}>
        <Link href="/admin" style={{ display: "block", fontWeight: 800, fontSize: 15, color: "var(--fg)", textDecoration: "none", marginBottom: 20, padding: "0 8px" }}>
          ⚡ signal·saas 后台
        </Link>
        {MENU.map((m) => {
          const active = pathname === m.href;
          return (
            <Link
              key={m.href}
              href={m.href}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "10px 12px",
                borderRadius: 6,
                fontSize: 13,
                marginBottom: 4,
                textDecoration: "none",
                color: active ? "var(--accent)" : "var(--muted)",
                background: active ? "var(--accent-soft)" : "transparent",
              }}
            >
              <span style={{ fontSize: 14 }}>{m.icon}</span>
              {m.label}
            </Link>
          );
        })}
        <button
          onClick={() => { tokenStore.clearAdmin(); router.push("/admin/login"); }}
          style={{
            marginTop: 24,
            width: "100%",
            padding: "10px",
            borderRadius: 6,
            border: "1px solid var(--rule)",
            background: "transparent",
            color: "var(--muted)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          退出登录
        </button>
      </aside>
      <main style={{ flex: 1, padding: 24, overflowX: "auto" }}>{children}</main>
    </div>
  );
}
