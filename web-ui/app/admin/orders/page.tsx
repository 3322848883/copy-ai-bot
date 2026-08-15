"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type OrderRow = {
  id: number; user_email: string; strategy_name: string; action: string; action_label: string;
  symbol: string; side: string; leverage: number; qty: number; required_margin_usdt: number;
  status: string; status_label: string; failure_category: string | null; latency_ms: number | null;
  executed_at: string | null;
};
type Kpi = { total: number; filled: number; failed: number; risk_blocked: number; fill_rate: number; avg_latency_ms: number | null };
type Failure = { kpi: Kpi; breakdown: Record<string, number> };

const ACTIONS = ["", "open", "add", "reduce", "close"];
const ACTION_LABEL: Record<string, string> = { "": "全部", open: "开仓", add: "加仓", reduce: "减仓", close: "平仓" };
const STATUSES = ["", "filled", "failed", "pending"];
const STATUS_LABEL: Record<string, string> = { "": "全部", filled: "已成交", failed: "已失败", pending: "待执行" };
const FAIL_CATS = ["balance", "permission", "leverage", "symbol", "min_size", "network", "price_deviation", "slippage", "risk", "other"];
const FAIL_NAMES: Record<string, string> = {
  balance: "余额不足", permission: "权限", leverage: "杠杆", symbol: "币对", min_size: "最小量",
  network: "网络", price_deviation: "价格偏差", slippage: "滑点", risk: "风控", other: "其他",
};

/** M5 跟单订单：全平台 CopyOrder 监控 + 失败归类报表。 */
export default function AdminOrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [action, setAction] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (action) params.set("action", action);
      if (status) params.set("status", status);
      const [r, f] = await Promise.all([
        apiFetch<{ items: OrderRow[] }>(`/admin/v1/orders?${params.toString()}`, {}, tokenStore.adminAccess),
        apiFetch<Failure>("/admin/v1/orders/failures", {}, tokenStore.adminAccess),
      ]);
      setOrders(r.items);
      setFailure(f);
    } catch { /* ignore */ }
  }, [action, status]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  const kpi = failure?.kpi;
  const maxFail = Math.max(1, ...Object.values(failure?.breakdown ?? {}));

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>跟单订单</div>
      <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>全平台监控 · CopyOrder · 写操作强制审计</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 16 }}>
        {[
          ["订单总数", kpi?.total ?? "-", "笔"],
          ["已成交", kpi?.filled ?? "-", `笔 · 成交率 ${kpi?.fill_rate ?? 0}%`],
          ["风控拦截", kpi?.risk_blocked ?? "-", "笔 · failure=risk"],
          ["执行失败", kpi?.failed ?? "-", "笔 · 已归类"],
          ["平均延迟", kpi?.avg_latency_ms != null ? `${kpi.avg_latency_ms}ms` : "-", "红线 10s / 5s"],
        ].map(([l, v, s]) => (
          <div key={l as string} className="card" style={{ padding: 16 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>{l as string}</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6, color: l === "执行失败" && (kpi?.failed ?? 0) > 0 ? "var(--danger)" : "var(--fg)" }}>{v as string}</div>
            <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}>{s as string}</div>
          </div>
        ))}
      </div>

      {/* 失败归类报表 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>失败归类报表 <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>/admin/v1/orders/failures</span></div>
        {Object.keys(failure?.breakdown ?? {}).length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>暂无失败订单</div>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {FAIL_CATS.filter((c) => (failure?.breakdown[c] ?? 0) > 0).map((c) => (
              <span key={c} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 20, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", fontSize: 12 }}>
                {FAIL_NAMES[c]} <b style={{ fontSize: 14 }}>{failure?.breakdown[c] ?? 0}</b>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 筛选 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        {ACTIONS.map((a) => (
          <button key={a} className="btn" style={{ padding: "6px 14px", fontSize: 12, border: action === a ? "1px solid var(--accent)" : "1px solid var(--rule)", color: action === a ? "var(--accent)" : "var(--muted)" }} onClick={() => { setAction(a); }}>{ACTION_LABEL[a]}</button>
        ))}
        <span style={{ color: "var(--muted)", fontSize: 12 }}>|</span>
        {STATUSES.map((s) => (
          <button key={s} className="btn" style={{ padding: "6px 14px", fontSize: 12, border: status === s ? "1px solid var(--accent)" : "1px solid var(--rule)", color: status === s ? "var(--accent)" : "var(--muted)" }} onClick={() => { setStatus(s); }}>{STATUS_LABEL[s]}</button>
        ))}
        <input className="input" style={{ width: 200, marginLeft: "auto" }} placeholder="搜索订单 ID" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {/* 订单列表 */}
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>用户</th><th style={th}>策略</th><th style={th}>动作</th><th style={th}>方向</th><th style={th}>币对</th><th style={th}>数量</th><th style={th}>保证金</th><th style={th}>状态</th><th style={th}>延迟</th>
            </tr>
          </thead>
          <tbody>
            {orders.filter((o) => !q || String(o.id).includes(q)).map((o) => (
              <tr key={o.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>#{o.id}</td>
                <td style={td}>{o.user_email}</td>
                <td style={td}>{o.strategy_name}</td>
                <td style={td}>
                  <span style={{ color: o.action === "close" ? "var(--danger)" : o.action === "add" ? "var(--warning)" : "var(--accent)" }}>{o.action_label}</span>
                </td>
                <td style={{ ...td, color: o.side === "long" ? "var(--success)" : o.side === "short" ? "var(--danger)" : "var(--muted)" }}>{o.side === "long" ? "多" : o.side === "short" ? "空" : "-"}</td>
                <td style={td}>{o.symbol || "-"}</td>
                <td style={td}>{o.qty} <span style={{ color: "var(--muted)", fontSize: 11 }}>×{o.leverage}</span></td>
                <td style={td}>{o.required_margin_usdt.toFixed(2)}</td>
                <td style={td}>
                  <span style={{ color: o.status === "filled" ? "var(--success)" : o.status === "failed" ? "var(--danger)" : "var(--warning)" }}>{o.status_label}</span>
                  {o.failure_category && <div style={{ fontSize: 11, color: "var(--muted)" }}>{FAIL_NAMES[o.failure_category] || o.failure_category}</div>}
                </td>
                <td style={td}>{o.latency_ms != null ? `${o.latency_ms}ms` : "-"}</td>
              </tr>
            ))}
            {orders.length === 0 && <tr><td colSpan={10} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无跟单订单</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };