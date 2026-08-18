"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { BrandMark, BrandName } from "@/components/Brand";
import { useWsChannel } from "@/components/WsProvider";

type Notif = { id: number; type: string; title: string; body: string | null; is_read: boolean; created_at?: string | null };

/** M5 T5.10 前台闭环：全局导航（品牌 logo + 真实通知铃铛 + 用户 chip + 1240 容器）。 */
export default function Nav() {
  const pathname = usePathname();
  const [loggedIn, setLoggedIn] = useState(false);
  const [subActive, setSubActive] = useState(false);
  const [subLeft, setSubLeft] = useState<number | null>(null);
  const [bellOpen, setBellOpen] = useState(false);
  const [notifs, setNotifs] = useState<Notif[]>([]);
  const [unread, setUnread] = useState(0);

  const loadNotifs = useCallback(async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("ss_access") : null;
    if (!token) {
      setNotifs([]);
      setUnread(0);
      return;
    }
    try {
      const r = await apiFetch<{ items: Notif[]; unread_count: number }>("/v1/notifications?limit=20", {}, token);
      setNotifs(r.items);
      setUnread(r.unread_count);
    } catch {
      /* 未登录/接口失败时保持空态 */
    }
  }, []);

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
      loadNotifs();
    }
  }, [pathname, loadNotifs]);

  // WS 实时：新站内消息 → 前插列表 + 未读数 +1
  useWsChannel("notification.new", useCallback((data: unknown) => {
    const n = data as Notif;
    if (!n || typeof n.id !== "number") return;
    setNotifs((prev) => [n, ...prev.filter((x) => x.id !== n.id)].slice(0, 20));
    setUnread((u) => u + 1);
  }, []));

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

  async function markRead(id: number) {
    const token = tokenStore.access;
    if (!token) return;
    try {
      await apiFetch(`/v1/notifications/${id}/read`, { method: "PATCH" }, token);
      setNotifs((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    } catch { /* ignore */ }
  }

  async function markAllRead() {
    const token = tokenStore.access;
    if (!token) return;
    try {
      await apiFetch("/v1/notifications/read-all", { method: "POST" }, token);
      setNotifs((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnread(0);
    } catch { /* ignore */ }
  }

  return (
    <nav
      className="topnav"
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
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--fg)", textDecoration: "none", whiteSpace: "nowrap" }}>
          <BrandMark />
          <BrandName />
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
                {unread > 0 && (
                  <span style={{ position: "absolute", top: 4, right: 4, minWidth: 15, height: 15, padding: "0 4px", borderRadius: 8, background: "var(--danger)", color: "#fff", fontSize: 9, display: "grid", placeItems: "center", fontFamily: "var(--font-geist-mono)" }}>
                    {unread > 99 ? "99+" : unread}
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
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>通知中心{unread > 0 && <span style={{ marginLeft: 6, fontSize: 10, color: "var(--accent)" }}>{unread} 条未读</span>}</div>
                          {notifs.some((n) => !n.is_read) && (
                            <button onClick={markAllRead} style={{ fontSize: 10, color: "var(--accent)", background: "transparent", border: "none", cursor: "pointer", padding: 0 }}>
                              全部已读
                            </button>
                          )}
                        </div>

                        {/* 订阅状态提示行 */}
                        {loggedIn && (
                          <div style={{ fontSize: 11, color: "var(--muted)", paddingBottom: 10, borderBottom: "1px solid var(--rule)" }}>
                            {subActive ? (
                              <>
                                <span className="badge badge-ok" style={{ marginRight: 6 }}>订阅中</span>
                                剩余 <strong style={{ color: "var(--fg)" }}>{subLeft ?? "—"}</strong> 天
                                {subLeft !== null && subLeft <= 3 && <span style={{ marginLeft: 6, color: "var(--warning)" }}>即将到期</span>}
                              </>
                            ) : (
                              <>
                                <span className="badge badge-warn" style={{ marginRight: 6 }}>未开通</span>
                                <Link href="/subscriptions" style={{ color: "var(--accent)", textDecoration: "none" }}>开通订阅开启跟单 →</Link>
                              </>
                            )}
                          </div>
                        )}

                        {/* 真实站内消息列表 */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 300, overflowY: "auto", margin: "0 -4px" }}>
                          {notifs.length === 0 && (
                            <div style={{ fontSize: 12, color: "var(--tertiary)", padding: "18px 0", textAlign: "center" }}>
                              暂无消息 · 奖励到账 / 提现状态 / 公告将实时推送至此
                            </div>
                          )}
                          {notifs.map((n) => (
                            <button
                              key={n.id}
                              onClick={() => { if (!n.is_read) markRead(n.id); }}
                              style={{
                                textAlign: "left", background: n.is_read ? "transparent" : "var(--accent-soft)", border: "none",
                                borderRadius: 6, padding: "8px 8px", cursor: n.is_read ? "default" : "pointer", display: "block", width: "100%",
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                {!n.is_read && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} />}
                                <span style={{ fontSize: 12, fontWeight: n.is_read ? 400 : 600, color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.title}</span>
                                <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--tertiary)", flexShrink: 0, fontFamily: "var(--font-geist-mono)" }}>
                                  {n.created_at ? new Date(n.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : ""}
                                </span>
                              </div>
                              {n.body && (
                                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3, lineHeight: 1.5, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                  {n.body}
                                </div>
                              )}
                            </button>
                          ))}
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
