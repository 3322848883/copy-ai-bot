"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Order = { id: number; user_id: number; plan_id: string; amount_usdt: number; network: string; tx_hash: string | null; status: string; confirmations: number; required: number; poll_attempts: number };

const STATUS_LABEL: Record<string, string> = {
  pending: "待支付", verifying: "校验中", polling: "轮询中", confirmed: "已确认",
  failed: "失败", manual: "待人工", timeout: "超时",
};

/** M5 T5.6 订单管理：支付订单列表 + manual 手动确认/标记失败。 */
export default function AdminPaymentsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Order[]>([]);
  const [status, setStatus] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async (st = status) => {
    try {
      const r = await apiFetch<{ items: Order[] }>(`/admin/v1/payments${st ? `?status=${st}` : ""}`, {}, tokenStore.adminAccess);
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

  async function manual(o: Order, result: string) {
    try {
      await apiFetch(`/admin/v1/payments/${o.id}/manual`, { method: "POST", body: JSON.stringify({ status: result }) }, tokenStore.adminAccess);
      setMsg(`#${o.id} 已人工${result === "confirmed" ? "确认" : "标记失败"}`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>订单管理</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {["", "manual", "polling", "confirmed", "failed"].map((s) => (
          <button key={s} className="btn" style={{ padding: "6px 14px", fontSize: 12, border: status === s ? "1px solid var(--accent)" : "1px solid var(--rule)", color: status === s ? "var(--accent)" : "var(--muted)" }} onClick={() => { setStatus(s); load(s); }}>
            {s === "" ? "全部" : STATUS_LABEL[s]}
          </button>
        ))}
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>用户</th><th style={th}>套餐</th><th style={th}>金额</th><th style={th}>网络</th><th style={th}>确认数</th><th style={th}>状态</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>#{o.id}</td>
                <td style={td}>{o.user_id}</td>
                <td style={td}>{o.plan_id}</td>
                <td style={{ ...td, fontWeight: 700 }}>{o.amount_usdt} U</td>
                <td style={td}>{o.network}</td>
                <td style={td}>{o.confirmations}/{o.required}（{o.poll_attempts}次）</td>
                <td style={td}>
                  <span style={{ color: o.status === "confirmed" ? "var(--success)" : o.status === "manual" ? "var(--warning)" : o.status === "failed" ? "var(--danger)" : "var(--muted)" }}>
                    {STATUS_LABEL[o.status] || o.status}
                  </span>
                </td>
                <td style={td}>
                  {(o.status === "manual" || o.status === "timeout") && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-primary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => manual(o, "confirmed")}>人工确认</button>
                      <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => manual(o, "failed")}>标记失败</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={8} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无订单</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
