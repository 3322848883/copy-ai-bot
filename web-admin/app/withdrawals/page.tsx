"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type Wd = { id: number; user_id: number; amount_usdt: number; fee_usdt: number; network: string; address: string; status: string; tx_hash: string | null; reject_reason: string | null; created_at: string | null };

const MONO = "var(--font-geist-mono), monospace";

/** 状态 → 徽章（对齐设计稿：待审核/已打款/已驳回/已退还/发放失败）。 */
const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending_review: { label: "待审核", cls: "badge-warn" },
  approved: { label: "已批准", cls: "badge-info" },
  processing: { label: "处理中", cls: "badge-info" },
  paid: { label: "已打款", cls: "badge-ok" },
  rejected: { label: "已驳回", cls: "badge-warn" },
  canceled: { label: "已取消", cls: "badge-muted" },
  expired: { label: "已过期", cls: "badge-muted" },
  paid_failed: { label: "发放失败", cls: "badge-err" },
  refunded: { label: "已退还", cls: "badge-muted" },
};

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "pending_review", label: "待审核" },
  { value: "approved", label: "已批准" },
  { value: "processing", label: "处理中" },
  { value: "paid", label: "已打款" },
  { value: "rejected", label: "已驳回" },
  { value: "paid_failed", label: "发放失败" },
  { value: "refunded", label: "已退还" },
];

const wdNo = (id: number) => `#W${String(id).padStart(8, "0")}`;
const shortTx = (tx: string) => (tx.length > 12 ? `${tx.slice(0, 6)}…${tx.slice(-4)}` : tx);

/** M5 T5.5 提现审核：KPI 卡 + 状态筛选 + 审核抽屉（approve/reject/fill-tx/retry/refund）。 */
export default function AdminWithdrawalsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const [items, setItems] = useState<Wd[]>([]);
  const [kpiItems, setKpiItems] = useState<Wd[]>([]);
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<Wd | null>(null);
  const [mode, setMode] = useState<"approve" | "reject">("approve");
  const [txHash, setTxHash] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (st = status) => {
    try {
      const [r, k] = await Promise.all([
        apiFetch<{ items: Wd[] }>(`/admin/v1/withdrawals${st ? `?status=${st}` : ""}`, {}, tokenStore.adminAccess),
        apiFetch<{ items: Wd[] }>("/admin/v1/withdrawals", {}, tokenStore.adminAccess),
      ]);
      setItems(r.items);
      setKpiItems(k.items);
    } catch {
      /* ignore */
    }
  }, [status]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  /** 统一执行写操作：confirm → API → toast → 关抽屉 → 刷新。 */
  async function run(fn: () => Promise<void>, okMsg: string, opts?: { title: string; message: string; danger?: boolean; confirmText?: string }) {
    if (opts) {
      const ok = await confirm(opts);
      if (!ok) return;
    }
    setBusy(true);
    try {
      await fn();
      toast("success", okMsg);
      closeDetail();
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  function openDetail(w: Wd) {
    setDetail(w);
    setMode("approve");
    setTxHash("");
    setRejectReason("");
  }
  function closeDetail() {
    setDetail(null);
  }

  const txValid = /^(0x[0-9a-fA-F]{40,}|[0-9a-fA-F]{64})$/.test(txHash.trim());

  /** 待审核通过：先 approve 再 fill-tx（后端 fill-tx 要求 approved/processing）。 */
  async function doApprove() {
    const w = detail;
    if (!w) return;
    const tx = txHash.trim();
    if (!tx) {
      toast("warn", "请填写 TxHash 后打款");
      return;
    }
    if (!txValid) {
      toast("warn", "TxHash 格式不正确");
      return;
    }
    await run(
      async () => {
        await apiFetch(`/admin/v1/withdrawals/${w.id}/approve`, { method: "POST", body: JSON.stringify({}) }, tokenStore.adminAccess);
        await apiFetch(`/admin/v1/withdrawals/${w.id}/fill-tx`, { method: "POST", body: JSON.stringify({ tx_hash: tx }) }, tokenStore.adminAccess);
      },
      `已通过 ${wdNo(w.id)} · TxHash 已记录 · 链上打款中 · 审计留痕`,
      {
        title: "通过并打款",
        message: `${wdNo(w.id)} · ${w.amount_usdt.toFixed(2)} USDT\n批准后填写 TxHash（${shortTx(tx)}）并进入链上打款，确认？`,
        danger: true,
        confirmText: "通过并打款",
      }
    );
  }

  /** 已批准/处理中：仅填 TxHash 确认发放。 */
  async function doFillTx() {
    const w = detail;
    if (!w) return;
    const tx = txHash.trim();
    if (!tx) {
      toast("warn", "请填写 TxHash 后确认发放");
      return;
    }
    if (!txValid) {
      toast("warn", "TxHash 格式不正确");
      return;
    }
    await run(
      async () => {
        await apiFetch(`/admin/v1/withdrawals/${w.id}/fill-tx`, { method: "POST", body: JSON.stringify({ tx_hash: tx }) }, tokenStore.adminAccess);
      },
      `已确认发放 ${wdNo(w.id)} · TxHash 已记录 · 审计留痕`,
      {
        title: "确认发放（TxHash）",
        message: `${wdNo(w.id)} · ${w.amount_usdt.toFixed(2)} USDT\n确认已手动转账并填写 TxHash（${shortTx(tx)}）？`,
        danger: true,
        confirmText: "确认发放",
      }
    );
  }

  async function doReject() {
    const w = detail;
    if (!w) return;
    const r = rejectReason.trim();
    if (!r) {
      toast("warn", "驳回必须填写原因");
      return;
    }
    await run(
      async () => {
        await apiFetch(`/admin/v1/withdrawals/${w.id}/reject`, { method: "POST", body: JSON.stringify({ reason: r }) }, tokenStore.adminAccess);
      },
      `已驳回 ${wdNo(w.id)} · 原因已通知用户 · 资金退回可提现余额 · 审计留痕`,
      {
        title: "拒绝提现",
        message: `${wdNo(w.id)} · ${w.amount_usdt.toFixed(2)} USDT\n原因：${r}\n拒绝后资金退回可用余额，确认拒绝？`,
        danger: true,
        confirmText: "确认驳回",
      }
    );
  }

  async function doRefund() {
    const w = detail;
    if (!w) return;
    await run(
      async () => {
        await apiFetch(`/admin/v1/withdrawals/${w.id}/refund`, { method: "POST", body: JSON.stringify({}) }, tokenStore.adminAccess);
      },
      `已退还申请 ${wdNo(w.id)} · 资金回退至可提现余额 · 审计留痕`,
      {
        title: "退还申请",
        message: `${wdNo(w.id)} · ${w.amount_usdt.toFixed(2)} USDT\n退还后资金回退，确认？`,
        danger: true,
        confirmText: "退还",
      }
    );
  }

  async function doRetry() {
    const w = detail;
    if (!w) return;
    await run(
      async () => {
        await apiFetch(`/admin/v1/withdrawals/${w.id}/retry`, { method: "POST", body: JSON.stringify({}) }, tokenStore.adminAccess);
      },
      `已重试 ${wdNo(w.id)} · 发放流程重新执行 · 审计留痕`,
      {
        title: "重试发放",
        message: `${wdNo(w.id)} · ${w.amount_usdt.toFixed(2)} USDT\n重试发放流程，确认？`,
        danger: true,
        confirmText: "重试",
      }
    );
  }

  function statusBadge(s: string) {
    const meta = STATUS_META[s];
    return <span className={`badge ${meta?.cls ?? "badge-muted"}`}>{meta?.label ?? s}</span>;
  }

  const pending = kpiItems.filter((x) => x.status === "pending_review");
  const paid = kpiItems.filter((x) => x.status === "paid");
  const rejected = kpiItems.filter((x) => x.status === "rejected");
  const refunded = kpiItems.filter((x) => x.status === "refunded");
  const sum = (arr: Wd[]) => arr.reduce((a, b) => a + b.amount_usdt, 0);

  const recent = kpiItems.filter((x) => x.status !== "pending_review").slice(0, 5);

  const kpiCards: { label: string; val: number; sub: string; color?: string }[] = [
    { label: "待审核", val: pending.length, sub: `笔 · 共 ${sum(pending).toFixed(2)} USDT` },
    { label: "今日已通过", val: paid.length, sub: "笔 · 已填 TxHash" },
    { label: "今日已驳回", val: rejected.length, sub: "笔 · 资金已退回" },
    { label: "已退还", val: refunded.length, sub: "笔 · 资金已回退", color: "var(--danger)" },
  ];

  const recentNote = (w: Wd): React.ReactNode => {
    if (w.tx_hash) return <span style={{ color: "var(--accent)" }}>{shortTx(w.tx_hash)}</span>;
    if (w.reject_reason) return <span style={{ color: "#f87171" }}>{w.reject_reason}</span>;
    switch (w.status) {
      case "refunded":
        return "资金已回退至可提现余额";
      case "paid_failed":
        return "转账失败，可重试";
      case "approved":
        return "等待填写 TxHash";
      case "processing":
        return "链上处理中";
      default:
        return "—";
    }
  };

  /** 抽屉里申请信息行。 */
  function infoRow(k: string, v: React.ReactNode, color?: string, extra?: React.CSSProperties) {
    return (
      <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12, gap: 12 }}>
        <span style={{ color: "var(--muted)", flexShrink: 0 }}>{k}</span>
        <span style={{ fontFamily: MONO, color, textAlign: "right", wordBreak: "break-all", ...extra }}>{v}</span>
      </div>
    );
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">WITHDRAWAL REVIEW · 提现审核</div>
          <h1 className="page-title">提现审核<small>{pending.length} 待审核 · 人工审核 + 链上打款</small></h1>
        </div>
      </div>

      {/* KPI 卡 */}
      <div className="kpi-grid">
        {kpiCards.map((c) => (
          <div key={c.label} className="kpi-card">
            <div className="kpi-l">{c.label}</div>
            <div className="kpi-v" style={c.color ? { color: c.color } : undefined}>{c.val}</div>
            <div className="kpi-s">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* 待审核列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>待审核列表</div>
          <span className="panel-sub">/admin/v1/withdrawals · approve/reject/fill-tx/retry/refund</span>
        </div>

        {/* 状态筛选 */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {FILTERS.map((f) => (
            <button
              key={f.value}
              className="btn"
              style={{
                padding: "6px 14px", fontSize: 12, borderRadius: 6,
                border: status === f.value ? "1px solid var(--accent)" : "1px solid var(--rule)",
                color: status === f.value ? "var(--accent)" : "var(--muted)",
                background: status === f.value ? "rgba(0,212,170,0.08)" : "transparent",
              }}
              onClick={() => {
                setStatus(f.value);
                load(f.value);
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>单号</th><th>用户</th><th className="num">金额</th><th>网络</th><th>风控</th><th>提交时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id} style={{ cursor: "pointer" }} onClick={() => openDetail(w)}>
                  <td style={{ fontFamily: MONO }}>{wdNo(w.id)}</td>
                  <td style={{ fontFamily: MONO }}>#{w.user_id}</td>
                  <td className="num">{w.amount_usdt.toFixed(2)}</td>
                  <td>{w.network}</td>
                  <td>
                    <span style={{ fontSize: 10, padding: "1px 8px", borderRadius: 4, fontFamily: MONO, background: "rgba(100,116,139,0.12)", color: "var(--tertiary)" }}>—</span>
                  </td>
                  <td className="sub-ref">{w.created_at?.slice(0, 16) || "-"}</td>
                  <td>
                    {w.status === "pending_review" && (
                      <button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); openDetail(w); }}>审核</button>
                    )}
                    {(w.status === "approved" || w.status === "processing") && (
                      <button className="action-link" onClick={(e) => { e.stopPropagation(); openDetail(w); }}>填 TxHash</button>
                    )}
                    {w.status === "paid_failed" && (
                      <button className="action-link danger" onClick={(e) => { e.stopPropagation(); openDetail(w); }}>重试 / 退款</button>
                    )}
                    {w.status === "rejected" && (
                      <button className="action-link danger" onClick={(e) => { e.stopPropagation(); openDetail(w); }}>退款</button>
                    )}
                    {["paid", "refunded", "canceled", "expired"].includes(w.status) && (
                      <button className="action-link" onClick={(e) => { e.stopPropagation(); openDetail(w); }}>详情</button>
                    )}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无提现单</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 最近处理记录 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>最近处理记录</div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>单号</th><th className="num">金额</th><th>状态</th><th>处理人</th><th>备注</th></tr>
            </thead>
            <tbody>
              {recent.map((w) => (
                <tr key={w.id}>
                  <td style={{ fontFamily: MONO }}>{wdNo(w.id)}</td>
                  <td className="num">{w.amount_usdt.toFixed(2)}</td>
                  <td>{statusBadge(w.status)}</td>
                  <td className="sub-ref">—</td>
                  <td className="sub-ref">{recentNote(w)}</td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无处理记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 审核抽屉（对齐设计稿 drawer，内联样式实现） */}
      {detail && (
        <>
          <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.6)", zIndex: 400 }} onClick={closeDetail} />
          <div
            style={{
              position: "fixed", top: 0, right: 0, bottom: 0, width: 480, maxWidth: "94vw", zIndex: 500,
              background: "var(--surface-overlay)", borderLeft: "1px solid var(--rule)",
              boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24,
              display: "flex", flexDirection: "column", gap: 16, overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 600, fontFamily: MONO }}>{wdNo(detail.id)}</div>
              <button className="modal-close" onClick={closeDetail}>✕</button>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{statusBadge(detail.status)}</div>

            {/* 申请信息 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>申请信息</div>
              {infoRow("用户", `#${detail.user_id}`)}
              {infoRow("提现金额", `${detail.amount_usdt.toFixed(2)} USDT`)}
              {infoRow("手续费", `${detail.fee_usdt.toFixed(2)} USDT`)}
              {infoRow("实际到账", `${(detail.amount_usdt - detail.fee_usdt).toFixed(2)} USDT`, "var(--success)")}
              {infoRow("网络", detail.network)}
              {infoRow("收款地址", detail.address)}
              {infoRow("提交时间", detail.created_at?.replace("T", " ").slice(0, 16) || "-")}
              {detail.tx_hash && infoRow("TxHash", detail.tx_hash, "var(--accent)")}
              {detail.reject_reason && infoRow("驳回原因", detail.reject_reason, "#f87171")}
            </div>

            {/* 审核操作区 */}
            {detail.status === "pending_review" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>审核操作</div>
                {mode === "approve" ? (
                  <div className="field">
                    <label className="field-label">通过后填写交易哈希 TxHash</label>
                    <input className="input" placeholder="9f 或 0x 开头的链上交易哈希" value={txHash} onChange={(e) => setTxHash(e.target.value)} />
                  </div>
                ) : (
                  <div className="field">
                    <label className="field-label">驳回原因（用户可见）</label>
                    <textarea className="input" placeholder="例：收款地址与实名不符，请重新提交" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                  </div>
                )}
                <div style={{ fontSize: 10, color: "var(--tertiary)" }}>提示：请按「实际到账」净额打款（链上校验以净额为下限），并核对收款地址</div>
              </div>
            )}
            {(detail.status === "approved" || detail.status === "processing") && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>确认发放</div>
                <div className="field">
                  <label className="field-label">交易哈希 TxHash</label>
                  <input className="input" placeholder="9f 或 0x 开头的链上交易哈希" value={txHash} onChange={(e) => setTxHash(e.target.value)} />
                </div>
                <div style={{ fontSize: 10, color: "var(--tertiary)" }}>提示：填写打款 TxHash 后确认发放；校验到账 ≥ 实际到账净额即通过</div>
              </div>
            )}

            {/* 操作按钮区 */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: "auto", paddingTop: 16, borderTop: "1px solid var(--rule)" }}>
              {detail.status === "pending_review" && (
                <>
                  <button
                    className="btn btn-secondary" style={{ flex: 1 }}
                    onClick={() => setMode(mode === "reject" ? "approve" : "reject")}
                  >
                    {mode === "reject" ? "改为通过" : "驳回"}
                  </button>
                  <button className="btn" style={{ flex: 1, background: "var(--warning)", color: "#332601" }} disabled={busy} onClick={doRefund}>退还申请</button>
                  <button
                    className="btn btn-primary" style={{ flex: 1 }} disabled={busy || (txHash.trim() !== "" && !txValid)}
                    onClick={mode === "reject" ? doReject : doApprove}
                  >
                    {mode === "reject" ? "确认驳回" : "通过并打款"}
                  </button>
                </>
              )}
              {(detail.status === "approved" || detail.status === "processing") && (
                <>
                  <button className="btn btn-secondary" style={{ flex: 1 }} onClick={closeDetail}>关闭</button>
                  <button className="btn btn-primary" style={{ flex: 1 }} disabled={busy || (txHash.trim() !== "" && !txValid)} onClick={doFillTx}>确认发放</button>
                </>
              )}
              {detail.status === "paid_failed" && (
                <>
                  <button className="btn btn-secondary" style={{ flex: 1 }} disabled={busy} onClick={doRetry}>重试</button>
                  <button className="btn btn-danger" style={{ flex: 1 }} disabled={busy} onClick={doRefund}>退还申请</button>
                </>
              )}
              {detail.status === "rejected" && (
                <>
                  <button className="btn btn-secondary" style={{ flex: 1 }} onClick={closeDetail}>关闭</button>
                  <button className="btn btn-danger" style={{ flex: 1 }} disabled={busy} onClick={doRefund}>退还申请</button>
                </>
              )}
              {["paid", "refunded", "canceled", "expired"].includes(detail.status) && (
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={closeDetail}>关闭</button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
