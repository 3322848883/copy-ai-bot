import type { CSSProperties } from "react";

/** 认证页（登录/注册）共享内联样式。
 *  对齐 .trae/documents/2026-08-12-signal-saas-auth.html 设计稿；
 *  设计稿独有组件（auth-tabs / steps / exchange-grid / glass card 等）在 globals.css 中不存在，
 *  因此全部以内联样式实现，不修改 globals.css。 */

/* ── 认证布局：左侧品牌区 + 右侧玻璃卡片（gridTemplateColumns 由页面按屏宽注入）── */
export const authWrap: CSSProperties = {
  position: "relative",
  zIndex: 1,
  width: "100%",
  margin: "0 auto",
  padding: "48px 24px",
  display: "grid",
  gap: 48,
  alignItems: "center",
};

/* ── 左侧品牌区 ── */
export const brandPanel: CSSProperties = { display: "flex", flexDirection: "column", gap: 24 };
export const brandLogo: CSSProperties = {
  display: "flex", alignItems: "center", gap: 12,
  fontWeight: 700, fontSize: 24, letterSpacing: "-0.01em", color: "var(--fg)",
};
export const brandMark: CSSProperties = {
  width: 40, height: 40, borderRadius: 6, display: "grid", placeItems: "center",
  background: "linear-gradient(135deg, #00d4aa, #009a7a)",
  boxShadow: "0 0 24px rgba(0,212,170,0.25)",
};
export const brandHero: CSSProperties = { fontSize: 34, fontWeight: 700, lineHeight: 1.25, letterSpacing: "-0.02em" };
export const brandFeats: CSSProperties = { display: "flex", flexDirection: "column", gap: 12 };
export const featRow: CSSProperties = { display: "flex", alignItems: "center", gap: 12, color: "var(--muted)", fontSize: 15 };
export const featIc: CSSProperties = {
  width: 28, height: 28, borderRadius: 6, background: "rgba(0,212,170,0.12)",
  color: "var(--accent)", display: "grid", placeItems: "center", fontSize: 13, flexShrink: 0,
};
export const brandWave: CSSProperties = { marginTop: 8, height: 70, position: "relative", opacity: 0.8 };

/* ── 右侧玻璃拟态认证卡片 ── */
export const authCard: CSSProperties = {
  background: "rgba(22,32,56,0.85)",
  backdropFilter: "blur(20px)",
  WebkitBackdropFilter: "blur(20px)",
  border: "1px solid rgba(51,65,85,0.6)",
  borderRadius: 10,
  boxShadow: "0 16px 48px rgba(0,0,0,0.45), 0 8px 20px rgba(0,0,0,0.3)",
  padding: 32,
  display: "flex",
  flexDirection: "column",
  gap: 16,
  width: "100%",
};

/* ── Tab 切换（滑动高亮）── */
export const tabsWrap: CSSProperties = {
  position: "relative",
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 4,
  background: "#070e1a",
  borderRadius: 6,
  padding: 4,
};
export const tabBtn: CSSProperties = {
  position: "relative",
  zIndex: 1,
  padding: "8px 0",
  border: "none",
  background: "transparent",
  fontSize: 15,
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 500,
  color: "var(--muted)",
  transition: "color 0.2s",
};
export const tabIndicator: CSSProperties = {
  position: "absolute",
  top: 4,
  bottom: 4,
  left: 4,
  width: "calc(50% - 6px)",
  background: "var(--accent)",
  borderRadius: 4,
  boxShadow: "0 0 24px rgba(0,212,170,0.25)",
  transition: "transform 0.25s ease",
  willChange: "transform",
};

/* ── 步骤指示器（含连线）── */
export const steps: CSSProperties = { display: "flex", alignItems: "center", justifyContent: "center", gap: 8 };
export const stepItem: CSSProperties = { display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--muted)" };
export const stepNum: CSSProperties = {
  width: 24, height: 24, borderRadius: "50%", border: "1px solid rgba(51,65,85,0.6)",
  display: "grid", placeItems: "center", fontFamily: "var(--font-geist-mono), monospace", fontSize: 11,
};
export const stepLine: CSSProperties = { width: 32, height: 1, background: "rgba(51,65,85,0.6)" };
export const stepActiveColor: CSSProperties = { color: "var(--fg)" };
export const stepActiveNum: CSSProperties = {
  background: "var(--accent)", borderColor: "var(--accent)", color: "#06281f",
  boxShadow: "0 0 24px rgba(0,212,170,0.25)",
};
export const stepDoneNum: CSSProperties = {
  background: "rgba(22,163,74,0.2)", borderColor: "var(--success)", color: "var(--success)",
};

/* ── 表单字段 / 输入 / 按钮（48px 规格）── */
export const field: CSSProperties = { display: "flex", flexDirection: "column", gap: 8 };
export const fieldLabel: CSSProperties = {
  fontSize: 12, color: "var(--muted)", fontWeight: 500,
  display: "flex", justifyContent: "space-between", alignItems: "center",
};
export const input48: CSSProperties = { height: 48 };
export const inputMono: CSSProperties = { fontFamily: "var(--font-geist-mono), monospace", fontSize: 14 };
export const btnPrimary48: CSSProperties = { height: 48, width: "100%", fontSize: 16, boxShadow: "0 0 24px rgba(0,212,170,0.25)" };
export const btnSecondary48: CSSProperties = { height: 48, width: "100%" };

/* ── 分隔 / 底部提示 ── */
export const divider: CSSProperties = { display: "flex", alignItems: "center", gap: 12, color: "var(--tertiary)", fontSize: 12 };
export const dividerLine: CSSProperties = { flex: 1, height: 1, background: "rgba(51,65,85,0.6)" };
export const authFoot: CSSProperties = { textAlign: "center", fontSize: 12, color: "var(--tertiary)" };
export const link: CSSProperties = { color: "var(--accent)", textDecoration: "none", cursor: "pointer" };

/* ── 校验码 ── */
export const codeRow: CSSProperties = { display: "flex", gap: 12 };
export const codeInput: CSSProperties = {
  flex: 1, letterSpacing: 10, textAlign: "center",
  fontFamily: "var(--font-geist-mono), monospace", fontSize: 20, fontWeight: 600, height: 48,
};
export const sendBtn: CSSProperties = { minWidth: 120, height: 48 };

/* ── 风险揭示 / 勾选行 ── */
export const riskBox: CSSProperties = {
  display: "flex", gap: 12, alignItems: "flex-start", padding: 12, borderRadius: 6,
  border: "1px solid rgba(234,179,8,0.3)", background: "rgba(234,179,8,0.06)",
  fontSize: 12, color: "var(--warning)", lineHeight: 1.6,
};
export const checkRow: CSSProperties = { display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--muted)", cursor: "pointer" };

/* ── 选所卡片 ── */
export const exchangeGrid: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 };
export const exchangeCard: CSSProperties = {
  border: "1px solid rgba(51,65,85,0.6)", borderRadius: 6, padding: 12, cursor: "pointer",
  display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
  transition: "all 0.2s", background: "#070e1a",
};
export const exchangeCardSel: CSSProperties = {
  borderColor: "var(--accent)", background: "rgba(0,212,170,0.08)",
  boxShadow: "0 0 0 3px rgba(0,212,170,0.12)",
};
export const exIc: CSSProperties = {
  width: 34, height: 34, borderRadius: 6, background: "var(--surface)",
  border: "1px solid rgba(51,65,85,0.6)", display: "grid", placeItems: "center",
  fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, fontWeight: 600, color: "var(--muted)",
};
export const exIcSel: CSSProperties = { borderColor: "var(--accent)", color: "var(--accent)" };
export const exName: CSSProperties = { fontSize: 10, color: "var(--muted)" };

/* ── 提示文字 / 标题 ── */
export const errMsg: CSSProperties = { fontSize: 12, color: "#f87171" };
export const okMsg: CSSProperties = { fontSize: 12, color: "var(--success)" };
export const subTitle: CSSProperties = { fontSize: 16, fontWeight: 600, color: "var(--fg)" };
export const subDesc: CSSProperties = { fontSize: 12, color: "var(--muted)" };
export const doneIcon: CSSProperties = { fontSize: 44, color: "var(--success)", textAlign: "center" };
