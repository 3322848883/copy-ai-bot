"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useWsChannel } from "@/components/WsProvider";

type Announcement = { id: number; title: string; body: string | null; level: string; pinned: boolean; published_at?: string | null };

const DISMISS_KEY = "ss_ann_dismissed";

const LEVEL_STYLE: Record<string, { bg: string; border: string; color: string; icon: string }> = {
  info: { bg: "rgba(0,212,170,0.08)", border: "rgba(0,212,170,0.35)", color: "#00d4aa", icon: "📣" },
  warning: { bg: "rgba(234,179,8,0.08)", border: "rgba(234,179,8,0.35)", color: "#eab308", icon: "⚠" },
  critical: { bg: "rgba(248,113,113,0.10)", border: "rgba(248,113,113,0.40)", color: "#f87171", icon: "🚨" },
};

/** 平台公告横幅：置顶/最新已发布公告，可关闭（按公告 id 记忆），登录态实时接收 WS 广播。 */
export default function AnnouncementBanner() {
  const pathname = usePathname();
  const [ann, setAnn] = useState<Announcement | null>(null);
  const [dismissed, setDismissed] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: Announcement[] }>("/v1/announcements?limit=1");
      const top = r.items[0] ?? null;
      setAnn(top);
      if (top) setExpanded(top.level === "critical" || top.level === "warning");
    } catch {
      setAnn(null);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setDismissed(Number(localStorage.getItem(DISMISS_KEY)) || null);
    }
    load();
  }, [pathname, load]);

  useWsChannel("announcement.new", useCallback((data: unknown) => {
    const a = data as Announcement;
    if (!a || typeof a.id !== "number") return;
    setAnn(a);
    setExpanded(true);
    if (typeof window !== "undefined") {
      localStorage.removeItem(DISMISS_KEY);
      setDismissed(null);
    }
  }, []));

  if (!ann || ann.id === dismissed) return null;
  if (pathname === "/login" || pathname === "/register") return null;

  const s = LEVEL_STYLE[ann.level] ?? LEVEL_STYLE.info;

  function dismiss() {
    if (typeof window !== "undefined") localStorage.setItem(DISMISS_KEY, String(ann!.id));
    setDismissed(ann!.id);
  }

  return (
    <div style={{ background: s.bg, borderBottom: `1px solid ${s.border}` }}>
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "8px 24px", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 13, flexShrink: 0 }}>{s.icon}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <button
            onClick={() => setExpanded((e) => !e)}
            style={{ background: "transparent", border: "none", cursor: "pointer", padding: 0, display: "block", width: "100%", textAlign: "left" }}
          >
            <span style={{ fontSize: 12.5, fontWeight: 600, color: s.color, display: "inline-flex", alignItems: "center", gap: 6 }}>
              {ann.pinned && <span style={{ fontSize: 10, border: `1px solid ${s.border}`, borderRadius: 2, padding: "0 4px" }}>置顶</span>}
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ann.title}</span>
              {ann.body && <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 400 }}>{expanded ? "收起 ▲" : "展开 ▼"}</span>}
            </span>
          </button>
          {expanded && ann.body && (
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7, marginTop: 4, whiteSpace: "pre-wrap" }}>{ann.body}</div>
          )}
        </div>
        <button
          onClick={dismiss}
          aria-label="关闭公告"
          style={{ flexShrink: 0, background: "transparent", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 14, padding: 4 }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
