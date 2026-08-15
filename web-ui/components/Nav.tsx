"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/** M5 T5.10 前台闭环：全局导航（后台 /admin 路径不渲染）。 */
export default function Nav() {
  const pathname = usePathname();
  const [loggedIn, setLoggedIn] = useState(false);
  const [subActive, setSubActive] = useState(false);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("ss_access") : null;
    setLoggedIn(!!token);
    if (token) {
      // ★ 修复：必须用 apiFetch（带 NEXT_PUBLIC_API_BASE 前缀），裸 fetch 会打到 Next 自身 404
      apiFetch<{ active: boolean }>("/v1/subscriptions/me", {}, token)
        .then((d) => setSubActive(!!d.active))
        .catch(() => setSubActive(false));
    }
  }, [pathname]);

  if (pathname?.startsWith("/admin") || pathname === "/login" || pathname === "/register") {
    return null;
  }

  const links = [
    { href: "/strategies", label: "策略广场" },
    { href: "/bots", label: "我的跟单" },
    { href: "/subscriptions", label: "订阅套餐", badge: !subActive && loggedIn ? "未开通" : undefined },
    { href: "/rewards", label: "奖励余额" },
    { href: "/invite", label: "邀请中心" },
  ];

  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "rgba(7,14,26,0.8)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 16px", minHeight: 56, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <Link href="/" style={{ fontWeight: 800, fontSize: 15, color: "var(--fg)", textDecoration: "none", whiteSpace: "nowrap" }}>
          signal·saas
        </Link>
        <div style={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end", minWidth: 0 }}>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{
                padding: "7px 9px",
                borderRadius: 6,
                fontSize: 12,
                textDecoration: "none",
                whiteSpace: "nowrap",
                color: pathname === l.href || pathname?.startsWith(l.href + "/") ? "var(--accent)" : "var(--muted)",
                background: pathname === l.href ? "var(--accent-soft)" : "transparent",
                position: "relative",
              }}
            >
              {l.label}
              {l.badge && (
                <span style={{ position: "absolute", top: 2, right: 2, fontSize: 9, color: "var(--warning)", background: "rgba(234,179,8,.15)", padding: "1px 5px", borderRadius: 8 }}>
                  {l.badge}
                </span>
              )}
            </Link>
          ))}
          {loggedIn ? (
            <Link href="/account" style={{ marginLeft: 6, padding: "7px 9px", fontSize: 12, color: "var(--muted)", textDecoration: "none", whiteSpace: "nowrap" }}>
              我的账户
            </Link>
          ) : (
            <Link href="/login" style={{ marginLeft: 6, padding: "7px 14px", fontSize: 12, color: "#fff", background: "var(--accent)", borderRadius: 6, textDecoration: "none", whiteSpace: "nowrap" }}>
              登录
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
