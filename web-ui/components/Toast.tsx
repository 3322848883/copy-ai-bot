"use client";

import { useCallback, useState } from "react";

/** 轻量 Toast：登录 / 注册 / 首次引导流程提示。
 *  样式与 app/page.tsx 首页 Toast 栈一致（内联实现，不依赖 globals.css 新增类）。 */

export type ToastType = "success" | "error" | "warn" | "info";
export interface ToastItem {
  id: number;
  type: ToastType;
  msg: string;
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const push = useCallback((type: ToastType, msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, type, msg }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return { toasts, push };
}

const borderColor: Record<ToastType, string> = {
  success: "rgba(40,196,100,0.4)",
  error: "rgba(239,68,68,0.4)",
  warn: "rgba(234,179,8,0.4)",
  info: "rgba(59,130,246,0.4)",
};
const fgColor: Record<ToastType, string> = {
  success: "var(--success)",
  error: "var(--danger)",
  warn: "var(--warning)",
  info: "#60a5fa",
};
const icon: Record<ToastType, string> = {
  success: "✓",
  error: "✕",
  warn: "!",
  info: "i",
};

export function ToastStack({ toasts }: { toasts: ToastItem[] }) {
  if (toasts.length === 0) return null;
  return (
    <div style={{ position: "fixed", top: 72, right: 20, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8 }}>
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            minWidth: 280,
            maxWidth: 360,
            padding: "12px 16px",
            borderRadius: 8,
            background: "var(--surface-overlay)",
            border: `1px solid ${borderColor[t.type]}`,
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 12,
            backdropFilter: "blur(16px)",
          }}
        >
          <span style={{ color: fgColor[t.type] }}>{icon[t.type]}</span>
          <span>{t.msg}</span>
        </div>
      ))}
    </div>
  );
}
