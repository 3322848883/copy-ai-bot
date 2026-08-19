"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";

type MenuItem = { href: string; label: string; icon: string; badge?: "signals" | "payments" | "withdrawals" | "risk" };

const MENU_GROUPS: { group: string; items: MenuItem[] }[] = [
  {
    group: "运营",
    items: [
      { href: "/", label: "数据概览", icon: "◈" },
      { href: "/users", label: "用户管理", icon: "▣" },
      { href: "/review", label: "主号审核", icon: "◈" },
      { href: "/strategies", label: "信号源审核", icon: "◈", badge: "signals" },
      { href: "/orders", label: "跟单订单", icon: "▤" },
      { href: "/payments", label: "支付记录", icon: "◎", badge: "payments" },
      { href: "/announcements", label: "公告管理", icon: "📣" },
    ],
  },
  {
    group: "财务",
    items: [
      { href: "/invites", label: "邀请奖励", icon: "⇄" },
      { href: "/wallets", label: "钱包账本", icon: "≋" },
      { href: "/withdrawals", label: "提现审核", icon: "↗", badge: "withdrawals" },
    ],
  },
  {
    group: "合作",
    items: [{ href: "/exchange-invites", label: "邀请码管理", icon: "🔑" }],
  },
  {
    group: "风控",
    items: [
      { href: "/risk", label: "风控中心", icon: "◉", badge: "risk" },
      { href: "/admins", label: "管理员管理", icon: "🛡" },
      { href: "/settings", label: "系统设置", icon: "⚙" },
      { href: "/audit", label: "审计日志", icon: "☰" },
      { href: "/signal-session", label: "信号源登录", icon: "🔐" },
    ],
  },
];

/** 独立后台布局：顶栏 + 分组侧栏（徽标）+ 内容区（aud=admin 独立会话）。 */
export default function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [badges, setBadges] = useState<Record<string, number>>({});
  const [searchKw, setSearchKw] = useState("");

  const loadBadges = useCallback(async () => {
    if (!tokenStore.adminAccess) return;
    try {
      const [sig, pay, wd, risk] = await Promise.all([
        apiFetch<{ items: unknown[] }>("/admin/v1/signals/pending", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
        apiFetch<{ total: number }>("/admin/v1/payments?status=pending&size=1", {}, tokenStore.adminAccess).catch(() => ({ total: 0 })),
        apiFetch<{ items: unknown[] }>("/admin/v1/withdrawals?status=pending", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
        apiFetch<{ items: unknown[] }>("/admin/v1/risk/high-risk", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
      ]);
      setBadges({ signals: sig.items.length, payments: pay.total, withdrawals: wd.items.length, risk: risk.items.length });
    } catch {
      /* 徽标失败不阻塞 */
    }
  }, []);

  useEffect(() => {
    if (pathname === "/login") return;
    loadBadges();
  }, [pathname, loadBadges]);

  if (pathname === "/login") return <>{children}</>;

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const kw = searchKw.trim();
    if (!kw) return;
    router.push(`/users?q=${encodeURIComponent(kw)}`);
  }

  return (
    <ToastProvider>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="bg-dots" />
      <div className="bg-sweep" />
      <div className="bg-noise" />

      <header className="topbar">
        <Link href="/" className="brand">
          <div className="brand-mark">
            <svg viewBox="0 0 32 32" fill="none" width={22} height={22}>
              <path d="M16 1.5 L29 9 V23 L16 30.5 L3 23 V9 Z" fill="#00d4aa" />
              <path d="M11 19.5 v-6 a5 5 0 1 1 10 0 v6 M8.5 22 h5 M18.5 22 h5" stroke="#06281f" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
            </svg>
          </div>
          Omni<span style={{ color: "var(--accent, #00d4aa)" }}>Alpha</span> <span className="admin-badge">ADMIN</span>
        </Link>
        <form className="top-search" onSubmit={onSearch}>
          <span className="s-ic">⌕</span>
          <input placeholder="全局搜索：用户 / 订单 / TxHash…" value={searchKw} onChange={(e) => setSearchKw(e.target.value)} />
        </form>
        <div className="top-right">
          <span className="audit-indicator">审计日志开启</span>
          <div className="admin-chip">
            <div className="admin-avatar">A</div>
            <span className="admin-name">admin</span>
          </div>
        </div>
      </header>

      <div className="shell">
        <aside className="sidebar">
          {MENU_GROUPS.map((g) => (
            <div key={g.group}>
              <div className="side-group">{g.group}</div>
              {g.items.map((m) => {
                const active = pathname === m.href;
                const badgeVal = m.badge ? badges[m.badge] : undefined;
                return (
                  <Link key={m.href} href={m.href} className={`side-item${active ? " active" : ""}`}>
                    <span className="side-ic">{m.icon}</span>
                    {m.label}
                    {badgeVal !== undefined && badgeVal > 0 && (
                      <span className={`side-badge${m.badge === "risk" ? " warn" : ""}`}>{badgeVal}</span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
          <div className="side-bottom">OmniAlpha Admin v1.0<br />JWT aud=admin</div>
          <button className="side-logout" onClick={() => { tokenStore.clearAdmin(); router.push("/login"); }}>
            退出登录
          </button>
        </aside>

        <main className="main">{children}</main>
      </div>
    </ToastProvider>
  );
}
