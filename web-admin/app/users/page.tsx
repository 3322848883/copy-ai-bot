"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type UserRow = {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  is_frozen: boolean;
  risk_disclosure_accepted?: boolean;
  created_at: string | null;
};
type HighRisk = { user_id: number; email: string; trigger: string; bind_1h: number; frozen_amount_usdt: number; status: string };
type Financial = {
  total_usdt: number;
  available_usdt: number;
  withdrawing_usdt: number;
  paid_usdt: number;
  frozen_usdt: number;
};
type UserDetail = UserRow & {
  exchange: string | null;
  identity_type: string | null;
  admin_note: string | null;
  financial: Financial;
  copy: { running_bots: number; today_orders: number; week_orders_count: number };
};
type ReviewDone = { id: number; action: string; target_id: string; actor_id: number; reason: string | null; created_at: string | null };

const ROLE_LABEL: Record<string, string> = { user: "普通用户", admin: "管理员", reviewer: "审核员", support: "客服" };

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "normal", label: "正常" },
  { key: "sub", label: "主号下级" },
  { key: "frozen", label: "已冻结" },
  { key: "risk", label: "风控标记" },
] as const;
type FilterKey = (typeof FILTERS)[number]["key"];

/** M5 T5.2 用户管理（对齐设计稿）：筛选 Tab + 搜索 + ftx-table + 详情抽屉（财务/跟单/风控）+ 冻结/解冻。 */
export default function AdminUsersPage() {
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [riskMap, setRiskMap] = useState<Record<number, HighRisk>>({});
  const [subIds, setSubIds] = useState<Set<number>>(new Set());
  const [drawer, setDrawer] = useState<UserRow | null>(null);
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [editingNote, setEditingNote] = useState(false);
  const [freezing, setFreezing] = useState(false);
  const [savingNote, setSavingNote] = useState(false);

  const openDrawer = useCallback(async (u: UserRow) => {
    setDrawer(u);
    setDetail(null);
    setEditingNote(false);
    try {
      const d = await apiFetch<UserDetail>(`/admin/v1/users/${u.id}`, {}, tokenStore.adminAccess);
      setDetail(d);
      setNoteDraft(d.admin_note ?? "");
    } catch {
      /* 详情加载失败时保留占位 */
    }
  }, []);

  async function saveNote() {
    if (!detail) return;
    setSavingNote(true);
    try {
      const r = await apiFetch<{ admin_note: string | null }>(
        `/admin/v1/users/${detail.id}/note`,
        { method: "PATCH", body: JSON.stringify({ note: noteDraft }) },
        tokenStore.adminAccess,
      );
      setDetail((prev) => (prev ? { ...prev, admin_note: r.admin_note } : prev));
      setEditingNote(false);
      toast("success", "备注已保存 · 操作已记入审计日志");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "保存失败");
    } finally {
      setSavingNote(false);
    }
  }

  const load = useCallback(async (query = "") => {
    try {
      const [u, r, d] = await Promise.all([
        apiFetch<{ items: UserRow[]; total: number }>(`/admin/v1/users?q=${encodeURIComponent(query)}&size=50`, {}, tokenStore.adminAccess),
        apiFetch<{ items: HighRisk[] }>("/admin/v1/risk/high-risk", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
        apiFetch<{ items: ReviewDone[] }>("/admin/v1/review/done", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
      ]);
      setItems(u.items);
      setTotal(u.total);
      setRiskMap(Object.fromEntries(r.items.map((x) => [x.user_id, x])));
      setSubIds(new Set(d.items.filter((x) => x.action === "review.approve").map((x) => Number(x.target_id))));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    // 顶栏全局搜索跳转 /users?q=… 时预填关键词
    const urlQ = new URLSearchParams(window.location.search).get("q") || "";
    setQ(urlQ);
    load(urlQ);
  }, [load, router]);

  const filtered = useMemo(() => {
    let list = items;
    if (filter === "normal") list = list.filter((u) => u.is_active && !u.is_frozen);
    else if (filter === "frozen") list = list.filter((u) => u.is_frozen);
    else if (filter === "sub") list = list.filter((u) => subIds.has(u.id));
    else if (filter === "risk") list = list.filter((u) => riskMap[u.id] !== undefined);
    return list;
  }, [items, filter, subIds, riskMap]);

  async function toggleFreeze(u: UserRow) {
    if (freezing) return;
    setFreezing(true);
    try {
      await apiFetch(`/admin/v1/users/${u.id}/freeze`, { method: "PATCH", body: JSON.stringify({ frozen: !u.is_frozen }) }, tokenStore.adminAccess);
      toast(u.is_frozen ? "success" : "warn", `用户 ${u.email} 已${u.is_frozen ? "解冻" : "冻结"} · 操作已记入审计日志`);
      await load(q);
      setDrawer((prev) => (prev && prev.id === u.id ? { ...prev, is_frozen: !u.is_frozen } : prev));
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    } finally {
      setFreezing(false);
    }
  }

  const fmtTime = (iso: string | null) => (iso ? `${iso.slice(5, 10)} ${iso.slice(11, 16)}` : "—");
  const roleBadge = (role: string) => {
    const label = ROLE_LABEL[role] || role;
    if (role === "admin") return <span className="badge badge-err">{label}</span>;
    if (role === "reviewer") return <span className="badge badge-info">{label}</span>;
    if (role === "support") return <span className="badge badge-warn">{label}</span>;
    return <span className="badge badge-muted">{label}</span>;
  };
  const statusBadge = (u: UserRow) =>
    u.is_frozen ? (
      <span className="badge badge-err">已冻结</span>
    ) : u.is_active ? (
      <span className="badge badge-ok">正常</span>
    ) : (
      <span className="badge badge-muted">未激活</span>
    );
  const subBadge = (u: UserRow) =>
    u.risk_disclosure_accepted === undefined ? (
      <span className="badge badge-muted">—</span>
    ) : u.risk_disclosure_accepted ? (
      <span className="badge badge-ok">已确认</span>
    ) : (
      <span className="badge badge-warn">未确认</span>
    );

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">USER MANAGEMENT</div>
          <h1 className="page-title">
            用户管理<small>{total.toLocaleString()} 位用户</small>
          </h1>
        </div>
        <div className="page-actions">
          <input
            className="input"
            style={{ width: 240 }}
            placeholder="邮箱搜索"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load(q)}
          />
          <button className="btn btn-primary" onClick={() => load(q)}>搜索</button>
        </div>
      </div>

      {/* 状态筛选 Tab */}
      <div
        style={{
          display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
          padding: "12px 16px", background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 8,
        }}
      >
        <span style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>筛选</span>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className="btn"
            style={{
              padding: "5px 14px", borderRadius: 999, height: "auto", minWidth: 0, fontSize: 12,
              border: filter === f.key ? "1px solid var(--admin-red-border)" : "1px solid var(--rule)",
              background: filter === f.key ? "rgba(239,68,68,0.1)" : "transparent",
              color: filter === f.key ? "var(--admin-red)" : "var(--muted)",
              fontWeight: filter === f.key ? 500 : 400,
            }}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
          {filter === "all" ? `共 ${total.toLocaleString()} 位` : `已筛选 ${filtered.length} / ${total.toLocaleString()} 位`}
        </span>
      </div>

      {/* 用户列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>用户列表</div>
          <span className="panel-sub">/admin/v1/users · 冻结/解冻强制审计留痕</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>身份</th>
                <th>风控确认</th>
                <th>状态</th>
                <th>注册时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)" }}>暂无用户</td>
                </tr>
              )}
              {filtered.map((u) => (
                <tr key={u.id} style={{ cursor: "pointer" }} onClick={() => openDrawer(u)}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{u.email}</td>
                  <td>{roleBadge(u.role)}</td>
                  <td>{subBadge(u)}</td>
                  <td>{statusBadge(u)}</td>
                  <td className="sub-ref">{fmtTime(u.created_at)}</td>
                  <td>
                    <button className="action-link" onClick={(e) => { e.stopPropagation(); openDrawer(u); }}>详情</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 详情抽屉（财务 / 跟单 / 风控） */}
      {drawer && (
        <div
          className="modal-overlay"
          style={{ justifyContent: "flex-end", alignItems: "stretch", padding: 0 }}
          onClick={() => setDrawer(null)}
        >
          <div
            style={{
              width: 460, maxWidth: "94vw", background: "var(--surface-overlay)", borderLeft: "1px solid var(--rule)",
              boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24,
              display: "flex", flexDirection: "column", gap: 16, overflowY: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-hdr">
              <div className="modal-title">{drawer.email}</div>
              <button className="modal-close" onClick={() => setDrawer(null)}>✕</button>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {statusBadge(drawer)}
              {roleBadge(drawer.role)}
              {riskMap[drawer.id] !== undefined && <span className="badge badge-err">风控标记</span>}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={secLabel}>基本信息</div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>用户 ID</span><span style={monoVal}>#{drawer.id}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>所选交易所</span><span style={monoVal}>{detail?.exchange || "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>注册时间</span><span style={monoVal}>{drawer.created_at?.slice(0, 16) || "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>身份类型</span><span style={monoVal}>{detail?.identity_type === "sub_account" ? "主号下级" : ROLE_LABEL[drawer.role] || drawer.role}</span></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={secLabel}>财务概览</div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>累计奖励</span><span style={monoVal}>{detail ? `${detail.financial.total_usdt.toFixed(2)} U` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>可提现余额</span><span style={monoVal}>{detail ? `${detail.financial.available_usdt.toFixed(2)} U` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>提现中</span><span style={monoVal}>{detail ? `${detail.financial.withdrawing_usdt.toFixed(2)} U` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>已提现</span><span style={monoVal}>{detail ? `${detail.financial.paid_usdt.toFixed(2)} U` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>冻结</span><span style={monoVal}>{detail ? `${detail.financial.frozen_usdt.toFixed(2)} U` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>风险确认</span><span style={monoVal}>{drawer.risk_disclosure_accepted === undefined ? "—" : drawer.risk_disclosure_accepted ? "已确认" : "未确认"}</span></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={secLabel}>跟单概览</div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>运行机器人</span><span style={monoVal}>{detail ? `${detail.copy.running_bots} 个` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>今日成交</span><span style={monoVal}>{detail ? `${detail.copy.today_orders} 单` : "—"}</span></div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>本周订单</span><span style={monoVal}>{detail ? `${detail.copy.week_orders_count} 单` : "—"}</span></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={secLabel}>风控标记</div>
              <div style={rowStyle}>
                <span style={{ color: "var(--muted)" }}>高危标记</span>
                <span>
                  {riskMap[drawer.id] !== undefined ? (
                    <span className="badge badge-err">有 · {riskMap[drawer.id].trigger}</span>
                  ) : (
                    <span className="badge badge-ok">无</span>
                  )}
                </span>
              </div>
              <div style={rowStyle}><span style={{ color: "var(--muted)" }}>1h 绑定数</span><span style={monoVal}>{riskMap[drawer.id] !== undefined ? riskMap[drawer.id].bind_1h : "—"}</span></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={secLabel}>管理员备注</div>
              {editingNote ? (
                <>
                  <textarea
                    className="input"
                    rows={3}
                    style={{ fontFamily: "inherit", resize: "vertical" }}
                    placeholder="记录该用户的备注信息…"
                    value={noteDraft}
                    onChange={(e) => setNoteDraft(e.target.value)}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-primary" style={{ flex: 1 }} disabled={savingNote} onClick={saveNote}>保存备注</button>
                    <button className="btn btn-secondary" style={{ flex: 1 }} disabled={savingNote} onClick={() => { setEditingNote(false); setNoteDraft(detail?.admin_note ?? ""); }}>取消</button>
                  </div>
                </>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ flex: 1, fontSize: 12, color: detail?.admin_note ? "var(--foreground)" : "var(--muted)", wordBreak: "break-all" }}>
                    {detail?.admin_note || "暂无备注"}
                  </span>
                  <button className="btn btn-secondary" style={{ padding: "5px 12px", height: "auto", minWidth: 0 }} onClick={() => setEditingNote(true)}>
                    {detail?.admin_note ? "编辑" : "添加"}
                  </button>
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: "auto" }}>
              {drawer.is_frozen ? (
                <button className="btn btn-primary" style={{ flex: 1 }} disabled={freezing} onClick={() => toggleFreeze(drawer)}>解冻用户</button>
              ) : (
                <button className="btn btn-danger" style={{ flex: 1 }} disabled={freezing} onClick={() => toggleFreeze(drawer)}>冻结用户</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const secLabel: React.CSSProperties = { fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 4 };
const rowStyle: React.CSSProperties = { display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 };
const monoVal: React.CSSProperties = { fontFamily: "var(--font-geist-mono), monospace" };
