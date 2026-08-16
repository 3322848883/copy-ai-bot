"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type ConfirmOptions = { title: string; message: string; danger?: boolean; confirmText?: string };
type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(() => Promise.resolve(false));

/** 全局确认弹窗 Provider：高危操作（资金/强制操作）二次确认。 */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((v: boolean) => void) | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    // ★ L1 修复：弹窗未关闭时忽略重复触发，避免首个 promise 永不 resolve
    if (resolverRef.current) return Promise.resolve(false);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState(opts);
    });
  }, []);

  const close = (result: boolean) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setState(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div style={{ position: "fixed", inset: 0, zIndex: 2000, background: "rgba(0,0,0,0.65)", display: "grid", placeItems: "center" }}>
          <div style={{ width: 420, maxWidth: "90vw", background: "#111d35", border: "1px solid var(--rule)", borderRadius: 12, padding: 24, boxShadow: "0 12px 40px rgba(0,0,0,0.5)" }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>{state.title}</div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 22, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{state.message}</div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button className="btn btn-secondary" style={{ padding: "8px 18px", fontSize: 13 }} onClick={() => close(false)}>取消</button>
              <button
                className="btn"
                style={{
                  padding: "8px 18px", fontSize: 13, border: "none",
                  background: state.danger ? "var(--danger)" : "var(--accent)",
                  color: "#fff", fontWeight: 600,
                }}
                onClick={() => close(true)}
              >
                {state.confirmText ?? "确认执行"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
