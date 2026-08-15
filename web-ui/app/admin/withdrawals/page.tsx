"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";

type Wd = { id: number; user_id: number; amount_usdt: number; fee_usdt: number; network: string; address: string; status: string; tx_hash: string | null; reject_reason: string | null; created_at: string | null };

const STATUS_LABEL: Record<string, string> = {
  pending_review: "待审核", approved: "已批准", processing: "处理中", paid: "已发放",
  rejected: "已拒绝", canceled: "已取消", expired: "已过期", paid_failed: "发放失败", refunded: "已退还",
};

/** M5 T5.5 提现审核：列表 + 5 动作（approve/reject/fill_tx/retry/refund）。 */
export default function AdminWithdrawalsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [items, setItems] = useState<Wd[]>([]);
  const [status, setStatus] = useState("");
  const [msg, setMsg] = useState("");
  const [reason, setReason] = useState<Record<number, string>>({});
  const [tx, setTx] = useState<Record<number, string>>({});

  const load = useCallback(async (st = status) => {
    try {
      const r = await apiFetch<{ items: Wd[] }>(`/admin/v1/withdrawals${st ? `?status=${st}` : ""}`, {}, tokenStore.adminAccess);
      setItems(r.items);
    } catch { /* ignore */ }
  }, [status]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function act(w: Wd, action: string, body?: object) {
    const plan: Record<string, { title: string; message: string; danger?: boolean; confirmText?: string }> = {
      approve: { title: "批准提现", message: `#${w.id} · 用户 #${w.user_id} · ${w.amount_usdt.toFixed(2)} USDT（实发 ${(w.amount_usdt - w.fee_usdt).toFixed(2)}）\n批准后进入发放流程，确认？`, confirmText: "批准" },
      reject: { title: "拒绝提现", message: `#${w.id} · ${w.amount_usdt.toFixed(2)} USDT\n拒绝后资金退回可用余额，确认拒绝？`, danger: true, confirmText: "拒绝" },
      "fill-tx": { title: "确认发放（TxHash）", message: `#${w.id} · ${w.amount_usdt.toFixed(2)} USDT\n确认已手动转账并填写 TxHash？`, danger: true, confirmText: "确认发放" },
      retry: { title: "重试发放", message: `#${w.id} · ${w.amount_usdt.toFixed(2)} USDT\n重试发放流程，确认？`, danger: true, confirmText: "重试" },
      refund: { title: "退还申请", message: `#${w.id} · ${w.amount_usdt.toFixed(2)} USDT\n退还后资金回退，确认？`, danger: true, confirmText: "退还" },
    };
    const p = plan[action];
    if (p) {
      const ok = await confirm({ ...p, message: p.message });
      if (!ok) return;
    }
    try {
      await apiFetch(`/admin/v1/withdrawals/${w.id}/${action}`, { method: "POST", body: JSON.stringify(body || {}) }, tokenStore.adminAccess);
      setMsg(`#${w.id} ${action} 成功`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>提现审核</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {["", "pending_review", "approved", "paid", "rejected"].map((s) => (
          <button key={s} className="btn" style={{ padding: "6px 14px", fontSize: 12, border: status === s ? "1px solid var(--accent)" : "1px solid var(--rule)", color: status === s ? "var(--accent)" : "var(--muted)" }} onClick={() => { setStatus(s); load(s); }}>
            {s === "" ? "全部" : STATUS_LABEL[s]}
          </button>
        ))}
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>用户</th><th style={th}>金额</th><th style={th}>网络</th><th style={th}>地址</th><th style={th}>状态</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>#{w.id}</td>
                <td style={td}>{w.user_id}</td>
                <td style={{ ...td, fontWeight: 700 }}>{w.amount_usdt.toFixed(2)} <span style={{ color: "var(--muted)", fontWeight: 400 }}>-{w.fee_usdt.toFixed(2)} 费</span></td>
                <td style={td}>{w.network}</td>
                <td style={{ ...td, fontSize: 11 }}>{w.address}</td>
                <td style={td}>
                  <span style={{ color: w.status === "paid" ? "var(--success)" : w.status === "rejected" ? "var(--danger)" : w.status === "pending_review" ? "var(--warning)" : "var(--muted)" }}>
                    {STATUS_LABEL[w.status] || w.status}
                  </span>
                </td>
                <td style={{ ...td, whiteSpace: "normal", minWidth: 300 }}>
                  {w.status === "pending_review" && (
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <button className="btn btn-primary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => act(w, "approve")}>批准</button>
                      <input className="input" style={{ width: 110, padding: "4px 8px", fontSize: 12 }} placeholder="拒绝理由" value={reason[w.id] || ""} onChange={(e) => setReason({ ...reason, [w.id]: e.target.value })} />
                      <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => act(w, "reject", { reason: reason[w.id] || "人工审核拒绝" })}>拒绝</button>
                    </div>
                  )}
                  {w.status === "approved" && (
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input className="input" style={{ width: 180, padding: "4px 8px", fontSize: 12 }} placeholder="TxHash" value={tx[w.id] || ""} onChange={(e) => setTx({ ...tx, [w.id]: e.target.value })} />
                      <button className="btn btn-primary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => act(w, "fill-tx", { tx_hash: tx[w.id] })} disabled={!tx[w.id]}>确认发放</button>
                    </div>
                  )}
                  {(w.status === "paid_failed" || w.status === "rejected") && (
                    <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => act(w, "retry")}>重试</button>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无提现单</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
