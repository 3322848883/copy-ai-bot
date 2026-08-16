"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type ToastType = "success" | "warn" | "error" | "info";
type ToastItem = { id: number; type: ToastType; message: string };

const ToastCtx = createContext<(type: ToastType, message: string) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

const ICONS: Record<ToastType, string> = { success: "✓", warn: "!", error: "✕", info: "i" };

/** 右上角 Toast 栈（对齐演示稿 .toast-stack）。 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const push = useCallback((type: ToastType, message: string) => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3200);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            <span className="t-ic">{ICONS[t.type]}</span>
            <span>{t.message}</span>
            <button className="t-close" onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}>✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
