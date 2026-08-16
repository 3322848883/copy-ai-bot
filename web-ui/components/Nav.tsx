"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/** M5 T5.10 前台闭环：全局导航（对齐设计稿：品牌 logo + 通知铃铛 + 用户 chip + 1240 容器）。 */
export default function Nav() {
  const pathname = usePathname();
  const [loggedIn, setLoggedIn] = useState(false);
  const [subActive, setSubActive] = useState(false);
  const [subLeft, setSubLeft] = useState<number | null>(null);
  const [bellOpen, setBellOpen] = useState(false);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("ss_access") : null;
    setLoggedIn(!!token);
    if (token) {
      apiFetch<{ active: boolean; days_left?: number; expires_at?: string }>("/v1/subscriptions/me", {}, token)
        .then((d) => {
          setSubActive(!!d.active);
          setSubLeft(d.days_left ?? null);
        })
        .catch(() => setSubActive(false));
    }
  }, [pathname]);

  if (pathname === "/login" || pathname === "/register") {
    return null;
  }

  const links = [
    { href: "/strategies", label: "策略广场" },
    { href: "/bots", label: "我的跟单" },
    { href: "/subscriptions", label: "订阅套餐", badge: !subActive && loggedIn ? "未开通" : undefined },
    { href: "/rewards", label: "奖励余额" },
    { href: "/invite", label: "邀请中心" },
  ];

  // 通知未读数：订阅将到期 / 未开通 提醒
  const noticeCount = loggedIn ? (subActive ? 0 : 1) : 0;

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
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "0 24px", minHeight: 56, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        {/* 品牌 logo */}
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 800, fontSize: 16, color: "var(--fg)", textDecoration: "none", whiteSpace: "nowrap" }}>
          <span
            style={{
              width: 28, height: 28, borderRadius: 6, display: "grid", placeItems: "center",
              background: "linear-gradient(135deg, var(--accent), #009a7a)", boxShadow: "0 0 18px rgba(0,212,170,0.3)",
            }}
          >
            <svg viewBox="0 0 16 16" width="16" height="16" fill="none">
              <path d="M1 9h3l2-6 3 10 2-5h4" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          signal·saas
        </Link>

        <div style={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end", minWidth: 0 }}>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{
                padding: "7px 10px",
                borderRadius: 6,
                fontSize: 12.5,
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

          {/* 通知铃铛 */}
          {loggedIn && (
            <div style={{ position: "relative", marginLeft: 6 }}>
              <button
                onClick={() => setBellOpen((o) => !o)}
                style={{
                  width: 34, height: 34, borderRadius: 8, border: "1px solid var(--rule)", background: "transparent",
                  color: "var(--muted)", cursor: "pointer", display: "grid", placeItems: "center", position: "relative", fontSize: 15,
                }}
                aria-label="通知"
              >
                🔔
                {noticeCount > 0 && (
                  <span style={{ position: "absolute", top: 4, right: 4, minWidth: 15, height: 15, padding: "0 4px", borderRadius: 8, background: "var(--danger)", color: "#fff", fontSize: 9, display: "grid", placeItems: "center", fontFamily: "var(--font-geist-mono)" }}>
                    {noticeCount}
                  </span>
                )}
              </button>
              {bellOpen && (
                <>
                  <div style={{ position: "fixed", inset: 0, zIndex: 9 }} onClick={() => setBellOpen(false)} />
                  <div
                    style={{
                      position: "absolute", right: 0, top: 40, width: 300, zIndex: 10, borderRadius: 10,
                      background: "var(--surface-overlay)", border: "1px solid var(--rule)", boxShadow: "0 16px 48px rgba(0,0,0,0.45)",
                      padding: 16, display: "flex", flexDirection: "column", gap: 12,
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>通知中心</div>
                    {subActive ? (
                      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7 }}>
                        <span className="badge badge-ok" style={{ marginRight: 8 }}>订阅中</span>
                        有效期剩余 <strong style={{ color: "var(--fg)" }}>{subLeft ?? "—"}</strong> 天
                        {subLeft !== null && subLeft <= 3 && (
                          <div style={{ marginTop: 6, color: "var(--warning)" }}>即将到期，请及时续费避免暂停开仓</div>
                        )}
                      </div>
                    ) : (
                      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7 }}>
                        <span className="badge badge-warn" style={{ marginRight: 8 }}>未开通</span>
                        开通订阅后即可开启跟单
                        <Link href="/subscriptions" style={{ display: "block", marginTop: 8, color: "var(--accent)", textDecoration: "none" }}>立即订阅 →</Link>
                      </div>
                    )}
                    <div style={{ paddingTop: 10, borderTop: "1px solid var(--rule)", fontSize: 10, color: "var(--tertiary)" }}>
                      奖励到账 / 新信号 / 提现状态等实时通知将在此汇聚
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* 用户 chip */}
          {loggedIn ? (
            <Link
              href="/account"
              style={{
                marginLeft: 6, display: "flex", alignItems: "center", gap: 8, padding: "4px 12px 4px 4px",
                border: "1px solid var(--rule)", borderRadius: 999, textDecoration: "none", whiteSpace: "nowrap",
              }}
            >
              <span
                style={{
                  width: 24, height: 24, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 700,
                  color: "#fff", background: "linear-gradient(135deg, var(--accent), #009a7a)",
                }}
              >
                U
              </span>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>我的账户</span>
            </Link>
          ) : (
            <Link href="/login" style={{ marginLeft: 6, padding: "7px 16px", fontSize: 12.5, color: "#06281f", background: "var(--accent)", borderRadius: 6, textDecoration: "none", whiteSpace: "nowrap", fontWeight: 600 }}>
              登录
            </Link>
          )}
          <span style={{ fontSize: 10, color: "var(--tertiary)", marginLeft: 8, whiteSpace: "nowrap" }}>
            <Link href="/privacy" style={{ color: "var(--tertiary)", textDecoration: "none" }}>隐私</Link>
            <span style={{ margin: "0 4px" }}>·</span>
            <Link href="/terms" style={{ color: "var(--tertiary)", textDecoration: "none" }}>条款</Link>
          </span>
        </div>
      </div>
    </nav>
  );
}
