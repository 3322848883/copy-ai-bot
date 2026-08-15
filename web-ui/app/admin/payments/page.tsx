"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";

type Order = { id: number; user_id: number; plan_id: string; amount_usdt: number; network: string; tx_hash: string | null; status: string; confirmations: number; required: number; poll_attempts: number };

type PAddr = { id: number; network: string; address: string; status: string; remark: string | null; updated_by: number | null; created_at: string | null };

const STATUS_LABEL: Record<string, string> = {
  pending: "待支付", verifying: "校验中", polling: "轮询中", confirmed: "已确认",
  failed: "失败", manual: "待人工", timeout: "超时",
};

const NETWORK_LABEL: Record<string, string> = { trc20: "TRC-20", bep20: "BEP-20", erc20: "ERC-20" };

/** M5 T5.6 订单管理：支付订单列表 + manual 手动确认/标记失败。 */
export default function AdminPaymentsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [items, setItems] = useState<Order[]>([]);
  const [status, setStatus] = useState("");
  const [msg, setMsg] = useState("");

  // ── 平台收款地址 ──
  const [addrs, setAddrs] = useState<PAddr[]>([]);
  const [form, setForm] = useState({ network: "trc20", address: "", remark: "" });

  const loadAddrs = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: PAddr[] }>("/admin/v1/payments/addresses", {}, tokenStore.adminAccess);
      setAddrs(r.items);
    } catch { /* ignore */ }
  }, []);

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
    loadAddrs();
  }, [load, loadAddrs, router]);

  async function manual(o: Order, result: string) {
    const ok = await confirm({
      title: result === "confirmed" ? "人工确认支付" : "标记订单失败",
      message: `订单 #${o.id}（${o.plan_id} · ${o.amount_usdt} USDT）\n确认${result === "confirmed" ? "支付到账并激活订阅？" : "支付失败？"}`,
      danger: result !== "confirmed",
      confirmText: result === "confirmed" ? "确认到账" : "标记失败",
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/payments/${o.id}/manual`, { method: "POST", body: JSON.stringify({ status: result }) }, tokenStore.adminAccess);
      setMsg(`#${o.id} 已人工${result === "confirmed" ? "确认" : "标记失败"}`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function createAddr() {
    if (!form.address.trim()) { setMsg("请填写收款地址"); return; }
    try {
      await apiFetch("/admin/v1/payments/addresses", { method: "POST", body: JSON.stringify(form) }, tokenStore.adminAccess);
      setMsg("收款地址已添加");
      setForm({ network: "trc20", address: "", remark: "" });
      loadAddrs();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "添加失败");
    }
  }

  async function toggleAddr(a: PAddr) {
    const ok = await confirm({
      title: a.status === "active" ? "停用收款地址" : "启用收款地址",
      message: `${NETWORK_LABEL[a.network] || a.network} · ${a.address}\n确认${a.status === "active" ? "停用" : "启用"}？`,
      danger: a.status === "active",
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/payments/addresses/${a.id}`, { method: "PATCH", body: JSON.stringify({ status: a.status === "active" ? "inactive" : "active" }) }, tokenStore.adminAccess);
      setMsg(`地址已${a.status === "active" ? "停用" : "启用"}`);
      loadAddrs();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function deleteAddr(a: PAddr) {
    const ok = await confirm({
      title: "删除收款地址",
      message: `${NETWORK_LABEL[a.network] || a.network} · ${a.address}\n删除后该地址不可恢复，确认删除？`,
      danger: true,
      confirmText: "删除",
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/payments/addresses/${a.id}`, { method: "DELETE" }, tokenStore.adminAccess);
      setMsg("收款地址已删除");
      loadAddrs();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "删除失败");
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

      {/* ── 平台收款地址（后台管理；支付校验读取 active 项）── */}
      <div style={{ fontSize: 18, fontWeight: 700, margin: "28px 0 12px" }}>平台收款地址</div>
      <div className="card" style={{ padding: 18, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <select className="btn" style={{ padding: "8px 12px", fontSize: 13 }} value={form.network} onChange={(e) => setForm({ ...form, network: e.target.value })}>
            {Object.entries(NETWORK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input
            style={{ flex: 1, minWidth: 260, padding: "8px 12px", fontSize: 13, background: "transparent", border: "1px solid var(--rule)", borderRadius: 8, color: "var(--fg)", fontFamily: "var(--font-geist-mono)" }}
            placeholder="收款地址（TRC-20: T 开头 34 位 / EVM: 0x + 40 hex）"
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
          <input
            style={{ flex: 1, minWidth: 140, padding: "8px 12px", fontSize: 13, background: "transparent", border: "1px solid var(--rule)", borderRadius: 8, color: "var(--fg)" }}
            placeholder="备注（可选）"
            value={form.remark}
            onChange={(e) => setForm({ ...form, remark: e.target.value })}
          />
          <button className="btn btn-primary" style={{ padding: "8px 16px", fontSize: 13 }} onClick={createAddr}>添加地址</button>
        </div>
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>网络</th><th style={th}>地址</th><th style={th}>状态</th><th style={th}>备注</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {addrs.map((a) => (
              <tr key={a.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>
                  <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 11, background: "rgba(0,212,170,0.1)", color: "var(--accent)" }}>{NETWORK_LABEL[a.network] || a.network}</span>
                </td>
                <td style={{ ...td, fontFamily: "var(--font-geist-mono)", fontSize: 12 }}>{a.address}</td>
                <td style={td}>
                  <span style={{ color: a.status === "active" ? "var(--success)" : "var(--muted)" }}>
                    {a.status === "active" ? "启用中" : "已停用"}
                  </span>
                </td>
                <td style={td}>{a.remark ?? "—"}</td>
                <td style={td}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => toggleAddr(a)}>
                      {a.status === "active" ? "停用" : "启用"}
                    </button>
                    <button className="btn" style={{ padding: "4px 10px", fontSize: 12, color: "var(--danger)", border: "1px solid rgba(239,68,68,0.4)" }} onClick={() => deleteAddr(a)}>删除</button>
                  </div>
                </td>
              </tr>
            ))}
            {addrs.length === 0 && <tr><td colSpan={5} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无收款地址，请添加</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
