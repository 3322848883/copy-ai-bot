"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type Summary = { total_usdt: number; available_usdt: number; withdrawing_usdt: number; paid_usdt: number; frozen_usdt: number };
type LedgerItem = { id: number; owner_id: number; owner_email: string; source_user_id: number; amount_usdt: number; status: string; status_label: string; created_at: string | null };

const MONO = "var(--font-geist-mono), monospace";

/** M5 钱包账本：★G12 全平台 5 字段 KPI + 流水明细 + 手动补发/扣除（高危写操作）。 */
export default function AdminWalletsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [adjust, setAdjust] = useState<{ mode: "credit" | "debit" } | null>(null);
  const [userId, setUserId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        apiFetch<Summary>("/admin/v1/wallets/summary", {}, tokenStore.adminAccess),
        apiFetch<{ items: LedgerItem[] }>("/admin/v1/wallets", {}, tokenStore.adminAccess),
      ]);
      setSummary(s);
      setLedger(l.items);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function submitAdjust() {
    const uid = parseInt(userId, 10);
    const amt = parseFloat(amount);
    if (!uid || !amt || amt <= 0 || !reason.trim()) {
      toast("warn", "请填写用户ID、金额与理由");
      return;
    }
    const signed = adjust?.mode === "debit" ? -amt : amt;
    const ok = await confirm({
      title: adjust?.mode === "debit" ? "手动扣除奖励" : "手动补发奖励",
      message: `用户 #${uid} ${adjust?.mode === "debit" ? "扣除" : "补发"} ${amt} USDT\n理由：${reason.trim()}\n该操作将写入账本与审计日志，确认执行？`,
      danger: true,
      confirmText: adjust?.mode === "debit" ? "确认扣除" : "确认补发",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await apiFetch("/admin/v1/wallets/adjust", { method: "POST", body: JSON.stringify({ user_id: uid, amount_usdt: signed, reason: reason.trim() }) }, tokenStore.adminAccess);
      toast("success", `已${adjust?.mode === "debit" ? "扣除" : "补发"} ${amt} USDT（用户 #${uid}）· 审计留痕`);
      setAdjust(null);
      setUserId("");
      setAmount("");
      setReason("");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  /** 来源列：手动调整（补发/扣除） vs 邀请奖励 / 退款回滚。 */
  function sourceLabel(l: LedgerItem) {
    if (l.source_user_id === l.owner_id) return l.amount_usdt >= 0 ? "手动补发" : "手动扣除";
    return l.amount_usdt < 0 ? "退款回滚" : "邀请奖励";
  }

  /** 状态徽章（对齐设计稿：核实中/已到账/冻结/已取消/提现中）。 */
  function statusBadge(l: LedgerItem) {
    switch (l.status) {
      case "available":
      case "paid":
        return <span className="badge badge-ok">{l.status_label}</span>;
      case "verifying":
        return <span className="badge badge-info">{l.status_label}</span>;
      case "withdrawing":
        return <span className="badge badge-muted">{l.status_label}</span>;
      case "frozen":
      case "paid_failed":
        return <span className="badge badge-err">{l.status_label}</span>;
      case "canceled":
      case "rolled_back":
        return <span className="badge badge-warn">{l.status_label}</span>;
      default:
        return <span className="badge badge-muted">{l.status_label}</span>;
    }
  }

  const cards: { label: string; val: number | undefined; sub: string; color?: string }[] = [
    { label: "累计奖励", val: summary?.total_usdt, sub: "USDT · 全平台" },
    { label: "可提现", val: summary?.available_usdt, sub: "USDT", color: "var(--success)" },
    { label: "提现中", val: summary?.withdrawing_usdt, sub: "USDT", color: "#60a5fa" },
    { label: "已提现", val: summary?.paid_usdt, sub: "USDT" },
    { label: "冻结", val: summary?.frozen_usdt, sub: "USDT · 48h 风控", color: "var(--danger)" },
  ];

  return (
    <div>
      {/* 页头 + 操作 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">REWARD LEDGER · 钱包账本</div>
          <h1 className="page-title">钱包账本<small>5 字段流水（G12）· 手动补发高危操作</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-danger" onClick={() => setAdjust({ mode: "debit" })}>手动扣除</button>
          <button className="btn btn-primary" onClick={() => setAdjust({ mode: "credit" })}>手动补发</button>
        </div>
      </div>

      {/* ★ G12 5 字段 KPI 卡 */}
      <div className="kpi-grid">
        {cards.map((c) => (
          <div key={c.label} className="kpi-card">
            <div className="kpi-l">{c.label}</div>
            <div className="kpi-v" style={c.color ? { color: c.color } : undefined}>
              {(c.val ?? 0).toFixed(2)}
            </div>
            <div className="kpi-s">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* 流水明细 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>奖励流水明细</div>
          <span className="panel-sub">/admin/v1/wallets · source: referral/manual/refund</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>时间</th><th>用户</th><th>来源</th><th className="num">金额</th><th>状态</th><th>关联</th></tr>
            </thead>
            <tbody>
              {ledger.map((l) => (
                <tr key={l.id}>
                  <td className="sub-ref">{l.created_at?.slice(0, 16) || "-"}</td>
                  <td style={{ fontFamily: MONO }}>{l.owner_email}</td>
                  <td>{sourceLabel(l)}</td>
                  <td className="num" style={{ color: l.amount_usdt >= 0 ? "var(--success)" : "#f87171" }}>
                    {l.amount_usdt >= 0 ? "+" : ""}{l.amount_usdt.toFixed(2)}
                  </td>
                  <td>{statusBadge(l)}</td>
                  <td className="sub-ref">{l.source_user_id === l.owner_id ? "人工调整 · 审计" : `#${l.id}`}</td>
                </tr>
              ))}
              {ledger.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无奖励流水</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 手动补发/扣除弹窗（对齐设计稿 modal） */}
      {adjust && (
        <div className="modal-overlay" style={{ zIndex: 500 }}>
          <div className="modal danger">
            <div className="modal-hdr">
              <div className="modal-title" style={{ color: "#f87171" }}>
                {adjust.mode === "debit" ? "手动扣除奖励" : "手动补发奖励"}
              </div>
              <button className="modal-close" onClick={() => setAdjust(null)}>✕</button>
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>手动调整用户奖励属高危操作：操作人 / 时间 / 金额 / 原因将写入审计日志，请谨慎核实</span>
            </div>
            <div className="field">
              <label className="field-label">目标用户</label>
              <input className="input" type="number" placeholder="用户 ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">金额（USDT）</label>
              <input className="input" type="number" placeholder="0.00" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">原因（必填）</label>
              <textarea className="input" placeholder="例：客服核实奖励漏发，补发 10 USDT" value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setAdjust(null)}>取消</button>
              <button className="btn btn-danger" style={{ flex: 1 }} disabled={busy} onClick={submitAdjust}>
                {adjust.mode === "debit" ? "确认扣除" : "确认补发"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
