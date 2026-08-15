"use client";

import { useState } from "react";

/** ★ T1.9 强制风险揭示模态：首次登录/首次开启跟单前必须勾选确认，不勾选不可继续。 */
export default function RiskDisclosureModal({
  open,
  onConfirm,
}: {
  open: boolean;
  onConfirm: () => void;
}) {
  const [checked, setChecked] = useState(false);
  if (!open) return null;

  return (
    <div style={styles.overlay}>
      <div style={styles.modal}>
        <h2 style={styles.title}>风险揭示与免责声明</h2>
        <div style={styles.body}>
          <p>1. 数字资产合约交易具有高风险，可能导致全部本金损失。</p>
          <p>2. 平台仅提供信号聚合与跟单工具，不承诺收益、不保本、不代客理财。</p>
          <p>3. 所有交易盈亏由您本人承担，平台不承担任何投资责任。</p>
          <p>4. 您必须充分了解杠杆交易机制、爆仓规则与市场风险。</p>
          <p>5. 您的资金始终在您本人的交易所账户内，平台不托管任何资金。</p>
        </div>
        <label style={styles.check}>
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          我已阅读并理解上述风险揭示，自愿承担所有交易风险
        </label>
        <div style={styles.actions}>
          <button
            style={checked ? styles.btnPrimary : { ...styles.btnPrimary, opacity: 0.4, cursor: "not-allowed" }}
            disabled={!checked}
            onClick={onConfirm}
          >
            确认并继续
          </button>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0, background: "rgba(7,14,26,0.78)", zIndex: 999,
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  modal: {
    width: 520, maxWidth: "92vw", background: "#162038", border: "1px solid #334155",
    borderRadius: 10, padding: 28, boxShadow: "0 16px 48px rgba(0,0,0,0.5)",
  },
  title: { color: "#f1f5f9", margin: "0 0 16px", fontSize: 18 },
  body: { color: "#94a3b8", fontSize: 13, lineHeight: 1.8, marginBottom: 16 },
  check: { display: "flex", gap: 8, alignItems: "flex-start", color: "#f1f5f9", fontSize: 13, marginBottom: 20 },
  actions: { display: "flex", justifyContent: "flex-end" },
  btnPrimary: {
    background: "#00d4aa", color: "#06281f", border: "none", borderRadius: 6,
    padding: "10px 24px", fontWeight: 600, cursor: "pointer", fontSize: 14,
  },
};
