"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type Order = { id: number; user_id: number; plan_id: string; amount_usdt: number; network: string; tx_hash: string | null; status: string; confirmations: number; required: number; poll_attempts: number; created_at: string | null };

type PAddr = { id: number; network: string; address: string; status: string; remark: string | null; updated_by: number | null; created_at: string | null };

const STATUS_LABEL: Record<string, string> = {
  pending: "待支付", verifying: "校验中", polling: "轮询中", confirmed: "已确认",
  failed: "失败", manual: "待人工", timeout: "确认超时",
};

const NETWORK_LABEL: Record<string, string> = { trc20: "TRC-20", bep20: "BEP-20", erc20: "ERC-20" };

/** 网络标签配色（对齐设计稿 net-tag trc/bep/erc）。 */
const NETWORK_STYLE: Record<string, React.CSSProperties> = {
  trc20: { color: "#00d4aa", borderColor: "rgba(0,212,170,0.4)" },
  bep20: { color: "#eab308", borderColor: "rgba(234,179,8,0.4)" },
  erc20: { color: "#60a5fa", borderColor: "rgba(59,130,246,0.4)" },
};

/** 状态筛选（保留原逻辑：全部/待人工/轮询中/已确认/失败）。 */
const FILTERS = ["", "manual", "polling", "confirmed", "failed"];

function netTag(network: string) {
  return (
    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 9, padding: "1px 8px", borderRadius: 2, border: "1px solid", color: "var(--muted)", ...(NETWORK_STYLE[network] ?? {}) }}>
      {NETWORK_LABEL[network] || network}
    </span>
  );
}

function statusBadge(status: string) {
  switch (status) {
    case "confirmed": return <span className="badge badge-ok">已确认</span>;
    case "failed": return <span className="badge badge-err">失败</span>;
    case "manual": return <span className="badge badge-warn">待人工</span>;
    case "timeout": return <span className="badge badge-warn">确认超时</span>;
    case "verifying":
    case "polling": return <span className="badge badge-info">{STATUS_LABEL[status]}</span>;
    default: return <span className="badge badge-muted">{STATUS_LABEL[status] || status}</span>;
  }
}

/** M5 T5.6 支付记录（对齐设计稿 admin-payments）：三链支付单列表 + 强制确认/标记失败 + 平台收款地址管理。 */
export default function AdminPaymentsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const [items, setItems] = useState<Order[]>([]);
  const [status, setStatus] = useState("");
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
      const [r, a] = await Promise.all([
        apiFetch<{ items: Order[] }>(`/admin/v1/payments${st ? `?status=${st}` : ""}`, {}, tokenStore.adminAccess),
        apiFetch<{ items: PAddr[] }>("/admin/v1/payments/addresses", {}, tokenStore.adminAccess),
      ]);
      setItems(r.items);
      setAddrs(a.items);
    } catch { /* ignore */ }
  }, [status]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

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
      toast("success", `#${o.id} 已人工${result === "confirmed" ? "确认" : "标记失败"}`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function createAddr() {
    if (!form.address.trim()) { toast("warn", "请填写收款地址"); return; }
    try {
      await apiFetch("/admin/v1/payments/addresses", { method: "POST", body: JSON.stringify(form) }, tokenStore.adminAccess);
      toast("success", "收款地址已添加（同网络旧地址已自动停用）");
      setForm({ network: "trc20", address: "", remark: "" });
      loadAddrs();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "添加失败");
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
      toast("success", `地址已${a.status === "active" ? "停用" : "启用"}`);
      loadAddrs();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
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
      toast("success", "收款地址已删除");
      loadAddrs();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "删除失败");
    }
  }

  const chipStyle = (active: boolean): React.CSSProperties => ({
    padding: "5px 14px", borderRadius: 999, border: "1px solid",
    borderColor: active ? "rgba(239,68,68,0.4)" : "var(--rule)",
    background: active ? "rgba(239,68,68,0.1)" : "transparent",
    color: active ? "var(--admin-red)" : "var(--muted)",
    fontSize: 12, fontWeight: active ? 500 : 400, cursor: "pointer", fontFamily: "inherit", transition: "all .15s",
  });

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">PAYMENT RECORDS · 支付记录</div>
          <h1 className="page-title">支付记录<small>三链支付 · 自动校验 + 人工介入</small></h1>
        </div>
      </div>

      {/* 状态筛选 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "12px 16px", background: "var(--surface-dim)", border: "1px solid var(--rule)", borderRadius: 8 }}>
        {FILTERS.map((s) => (
          <button key={s} style={chipStyle(status === s)} onClick={() => { setStatus(s); load(s); }}>
            {s === "" ? "全部" : STATUS_LABEL[s]}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
          {items.length} 笔
        </span>
      </div>

      {/* 支付订单列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>支付订单列表</div>
          <span className="panel-sub">/admin/v1/payments · manual-confirm 需审计</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>订单号</th><th>用户</th><th>套餐</th><th className="num" style={{ textAlign: "right" }}>金额</th>
                <th>网络</th><th>TxHash</th><th>状态</th><th className="num" style={{ textAlign: "right" }}>确认数</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>#{o.id}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>用户 #{o.user_id}</td>
                  <td>{o.plan_id}</td>
                  <td className="num">{o.amount_usdt.toFixed(2)} <span className="sub-ref">USDT</span></td>
                  <td>{netTag(o.network)}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }} title={o.tx_hash ?? undefined}>
                    {o.tx_hash || <span style={{ color: "var(--tertiary)" }}>—</span>}
                  </td>
                  <td>{statusBadge(o.status)}</td>
                  <td className="num">{o.confirmations}/{o.required} <span className="sub-ref">（{o.poll_attempts} 次）</span></td>
                  <td>
                    {o.status === "manual" || o.status === "timeout" ? (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-danger btn-sm" onClick={() => manual(o, "confirmed")}>强制确认</button>
                        <button className="btn btn-secondary btn-sm" onClick={() => manual(o, "failed")}>标记失败</button>
                      </div>
                    ) : (
                      <span style={{ color: "var(--tertiary)", fontSize: 10 }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无支付订单</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* 平台收款地址 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>平台收款地址</div>
          <span className="panel-sub">/admin/v1/payments/addresses · 每网络仅 1 个 active</span>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
          <select className="select" style={{ width: 140 }} value={form.network} onChange={(e) => setForm({ ...form, network: e.target.value })}>
            {Object.entries(NETWORK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input
            className="input"
            style={{ flex: 1, minWidth: 260, height: 36, fontFamily: "var(--font-geist-mono), monospace", fontSize: 12 }}
            placeholder="收款地址（TRC-20: T 开头 34 位 / EVM: 0x + 40 hex）"
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
          <input
            className="input"
            style={{ flex: 1, minWidth: 140, height: 36 }}
            placeholder="备注（可选）"
            value={form.remark}
            onChange={(e) => setForm({ ...form, remark: e.target.value })}
          />
          <button className="btn btn-primary" style={{ height: 36, padding: "0 20px", fontSize: 13 }} onClick={createAddr}>添加地址</button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>网络</th><th>地址</th><th>状态</th><th>备注</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {addrs.map((a) => (
                <tr key={a.id}>
                  <td>{netTag(a.network)}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11 }}>{a.address}</td>
                  <td>{a.status === "active" ? <span className="badge badge-ok">启用中</span> : <span className="badge badge-muted">已停用</span>}</td>
                  <td>{a.remark ?? "—"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="action-link" onClick={() => toggleAddr(a)}>{a.status === "active" ? "停用" : "启用"}</button>
                      <button className="action-link danger" onClick={() => deleteAddr(a)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
              {addrs.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无收款地址，请添加</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
