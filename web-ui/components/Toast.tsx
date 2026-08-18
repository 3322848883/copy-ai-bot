"use client";

import { useCallback, useState } from "react";

/** 全站统一 Toast（globals.css .toast-stack/.toast 样式，带入场动画与关闭按钮）。 */

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
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  return { toasts, push, dismiss };
}

const ICON: Record<ToastType, string> = { success: "✓", error: "✕", warn: "!", info: "i" };

export function ToastStack({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss?: (id: number) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type}`}>
          <span className="t-ic">{ICON[t.type]}</span>
          <span>{t.msg}</span>
          {onDismiss && (
            <button className="t-close" onClick={() => onDismiss(t.id)} aria-label="关闭">
              ✕
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
