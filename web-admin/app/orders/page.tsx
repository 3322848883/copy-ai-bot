"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type OrderRow = {
  id: number; user_email: string; strategy_name: string; action: string; action_label: string;
  symbol: string; side: string; leverage: number; qty: number; required_margin_usdt: number;
  status: string; status_label: string; failure_category: string | null; fail_reason?: string | null;
  latency_ms: number | null; created_at?: string | null; executed_at: string | null;
};
type Kpi = { total: number; filled: number; failed: number; risk_blocked: number; fill_rate: number; avg_latency_ms: number | null };
type Failure = { kpi: Kpi; breakdown: Record<string, number> };

const PAGE_SIZE = 50;

/** 动作筛选（"全部"同时复位动作与状态，对齐设计稿单条 全部 语义）。 */
const ACTIONS = ["", "open", "add", "reduce", "close"];
const ACTION_LABEL: Record<string, string> = { "": "全部", open: "开仓", add: "加仓", reduce: "减仓", close: "平仓" };
const STATUSES = ["filled", "failed", "pending"];
const STATUS_LABEL: Record<string, string> = { filled: "已成交", failed: "已失败", pending: "待执行" };

/** 设计稿失败归类报表：failure_category 枚举（risk 由 KPI「风控拦截」单独展示；
 *  no_position=带单员平/减仓时本账户无该仓位，2026-08-20 从 other 拆出——常见于中途开始跟单，属预期状态不匹配）。 */
const FAIL_CATS = ["balance", "permission", "leverage", "symbol", "min_size", "network", "price_deviation", "slippage", "no_position", "other"];
const FAIL_NAMES: Record<string, string> = {
  balance: "余额不足", permission: "权限", leverage: "杠杆", symbol: "币对", min_size: "最小量",
  network: "网络", price_deviation: "价格偏差", slippage: "滑点", risk: "风控",
  no_position: "无持仓", other: "其他",
};

/** 动作标签配色（对齐设计稿 act-open/add/reduce/close）。 */
const ACTION_TAG_STYLE: Record<string, React.CSSProperties> = {
  open: { background: "rgba(22,163,74,0.12)", color: "#28c464" },
  add: { background: "rgba(0,212,170,0.12)", color: "#00d4aa" },
  reduce: { background: "rgba(234,179,8,0.12)", color: "#eab308" },
  close: { background: "rgba(239,68,68,0.12)", color: "#f87171" },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** 后端未返回成交价：由 required_margin × leverage / qty 估算（开仓单 qty 即按该式推导）。 */
function estPrice(o: OrderRow): number | null {
  if (!o.qty || !o.required_margin_usdt || !o.leverage) return null;
  return (o.required_margin_usdt * o.leverage) / o.qty;
}
function fmtPrice(p: number | null): string {
  if (p == null) return "-";
  if (p >= 1000) return p.toLocaleString("en-US", { maximumFractionDigits: 1 });
  if (p >= 1) return p.toFixed(2);
  return p.toFixed(4);
}

function statusBadge(o: OrderRow) {
  if (o.status === "filled") return <span className="badge badge-ok">已成交</span>;
  if (o.status === "failed") {
    if (o.failure_category === "risk") return <span className="badge badge-warn">风控拦截</span>;
    return <span className="badge badge-err">已失败</span>;
  }
  if (o.status === "pending") return <span className="badge badge-info">待执行</span>;
  return <span className="badge badge-muted">{o.status_label || o.status}</span>;
}

/** M5 跟单订单（对齐设计稿 admin-orders）：CopyOrder 全量监控 + 失败归类报表（九类枚举）。 */
export default function AdminOrdersPage() {
  const router = useRouter();
  const toast = useToast();
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [action, setAction] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (action) params.set("action", action);
      if (status) params.set("status", status);
      params.set("page", String(page));
      params.set("size", String(PAGE_SIZE));
      const [r, f] = await Promise.all([
        apiFetch<{ total: number; items: OrderRow[] }>(`/admin/v1/orders?${params.toString()}`, {}, tokenStore.adminAccess),
        apiFetch<Failure>("/admin/v1/orders/failures", {}, tokenStore.adminAccess),
      ]);
      setOrders(r.items);
      setTotal(r.total);
      setFailure(f);
    } catch { /* ignore */ }
  }, [action, status, page]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  const kpi = failure?.kpi;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const extraCats = Object.keys(failure?.breakdown ?? {}).filter((c) => !FAIL_CATS.includes(c));

  const chipStyle = (active: boolean): React.CSSProperties => ({
    padding: "5px 14px", borderRadius: 999, border: "1px solid",
    borderColor: active ? "rgba(239,68,68,0.4)" : "var(--rule)",
    background: active ? "rgba(239,68,68,0.1)" : "transparent",
    color: active ? "var(--admin-red)" : "var(--muted)",
    fontSize: 12, fontWeight: active ? 500 : 400, cursor: "pointer", fontFamily: "inherit", transition: "all .15s",
  });
  const pageBtn = (active: boolean): React.CSSProperties => ({
    width: 32, height: 32, borderRadius: 4, border: "1px solid",
    borderColor: active ? "rgba(239,68,68,0.4)" : "var(--rule)",
    background: active ? "rgba(239,68,68,0.1)" : "transparent",
    color: active ? "var(--admin-red)" : "var(--muted)",
    cursor: "pointer", fontFamily: "var(--font-geist-mono), monospace", fontSize: 12,
  });

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">COPY ORDERS · 跟单订单</div>
          <h1 className="page-title">跟单订单<small>全平台监控 · CopyOrder</small></h1>
        </div>
      </div>

      {/* KPI */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-l">今日订单</div>
          <div className="kpi-v">{kpi ? kpi.total.toLocaleString() : "-"}</div>
          <div className="kpi-s">笔 · 成交率 {kpi?.fill_rate ?? 0}%</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">已成交</div>
          <div className="kpi-v">{kpi ? kpi.filled.toLocaleString() : "-"}</div>
          <div className="kpi-s">笔 · filled</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">风控拦截</div>
          <div className="kpi-v">{kpi ? kpi.risk_blocked.toLocaleString() : "-"}</div>
          <div className="kpi-s">笔 · failure=risk</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">执行失败</div>
          <div className="kpi-v" style={(kpi?.failed ?? 0) > 0 ? { color: "#f87171" } : undefined}>{kpi ? kpi.failed.toLocaleString() : "-"}</div>
          <div className="kpi-s">笔 · 已归类</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">平均延迟</div>
          <div className="kpi-v">{kpi?.avg_latency_ms != null ? `${kpi.avg_latency_ms}ms` : "-"}</div>
          <div className="kpi-s">红线 10s / 5s</div>
        </div>
      </div>

      {/* 失败归类报表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>失败归类报表</div>
          <span className="panel-sub">/admin/v1/orders/failures · failure_category 枚举</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {FAIL_CATS.map((c) => (
            <span key={c} style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--rule)", color: "var(--muted)", display: "inline-flex", alignItems: "center", gap: 6 }}>
              {FAIL_NAMES[c]} <b style={{ fontWeight: 600, color: "#f87171" }}>{failure?.breakdown[c] ?? 0}</b>
            </span>
          ))}
          {extraCats.map((c) => (
            <span key={c} style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, padding: "3px 10px", borderRadius: 4, border: "1px solid rgba(239,68,68,0.3)", color: "var(--muted)", display: "inline-flex", alignItems: "center", gap: 6 }}>
              {FAIL_NAMES[c] || c} <b style={{ fontWeight: 600, color: "#f87171" }}>{failure?.breakdown[c] ?? 0}</b>
            </span>
          ))}
        </div>
      </div>

      {/* 订单列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>订单列表</div>
          <span className="panel-sub">按动作/状态/交易所筛选</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "12px 16px", background: "var(--surface-dim)", border: "1px solid var(--rule)", borderRadius: 8, marginBottom: 16 }}>
          {ACTIONS.map((a) => (
            <button
              key={a}
              style={chipStyle(a === "" ? action === "" && status === "" : action === a)}
              onClick={() => {
                if (a === "") { setAction(""); setStatus(""); } else { setAction(a); }
                setPage(1);
                toast("info", `已筛选：${ACTION_LABEL[a]}`);
              }}
            >
              {ACTION_LABEL[a]}
            </button>
          ))}
          <span style={{ fontSize: 10, color: "var(--tertiary)" }}>|</span>
          {STATUSES.map((s) => (
            <button
              key={s}
              style={chipStyle(status === s)}
              onClick={() => { setStatus(s); setPage(1); toast("info", `已筛选：${STATUS_LABEL[s]}`); }}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
            {total > 0 ? `共 ${total.toLocaleString()} 笔` : "显示最近 50 笔"}
          </span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>时间</th><th>用户</th><th>策略</th><th>动作</th><th>方向</th>
                <th className="num" style={{ textAlign: "right" }}>币对</th><th className="num" style={{ textAlign: "right" }}>数量</th>
                <th className="num" style={{ textAlign: "right" }}>价格</th><th>状态</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="sub-ref" title={o.executed_at ? "成交时间" : "下单时间"}>{fmtTime(o.executed_at ?? o.created_at ?? null)}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{o.user_email}</td>
                  <td>{o.strategy_name || "-"}</td>
                  <td>
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, padding: "1px 8px", borderRadius: 2, ...(ACTION_TAG_STYLE[o.action] ?? { background: "rgba(100,116,139,0.12)", color: "var(--muted)" }) }}>
                      {o.action_label || o.action}
                    </span>
                  </td>
                  <td style={{ color: o.side === "long" ? "#28c464" : o.side === "short" ? "#f87171" : "var(--muted)" }}>
                    {o.side === "long" ? "多" : o.side === "short" ? "空" : "-"}
                  </td>
                  <td className="num">{o.symbol || "-"}</td>
                  <td className="num">{o.qty != null ? o.qty : "-"}{o.leverage ? <span className="sub-ref"> ×{o.leverage}</span> : null}</td>
                  <td className="num">{fmtPrice(estPrice(o))}</td>
                  <td>
                    {statusBadge(o)}
                    {o.status === "failed" && o.failure_category && (
                      <div className="sub-ref">{FAIL_NAMES[o.failure_category] || o.failure_category}</div>
                    )}
                    {/* ★ 具体失败原因（2026-08-20）：交易所原始报错/风控规则/校验消息，悬停看全文 */}
                    {o.status === "failed" && o.fail_reason && (
                      <div
                        className="sub-ref"
                        style={{ maxWidth: 260, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                        title={o.fail_reason}
                      >
                        {o.fail_reason}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {orders.length === 0 && <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无跟单订单</td></tr>}
            </tbody>
          </table>
        </div>
        {pageCount > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
            <button style={pageBtn(false)} disabled={page === 1} onClick={() => setPage(Math.max(1, page - 1))}>‹</button>
            {Array.from({ length: pageCount }, (_, i) => i + 1).slice(0, 7).map((p) => (
              <button key={p} style={pageBtn(page === p)} onClick={() => setPage(p)}>{p}</button>
            ))}
            <button style={pageBtn(false)} disabled={page === pageCount} onClick={() => setPage(Math.min(pageCount, page + 1))}>›</button>
          </div>
        )}
      </div>
    </div>
  );
}
