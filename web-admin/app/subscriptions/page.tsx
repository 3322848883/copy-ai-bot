"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type Sub = {
  id: number; user_id: number; email: string | null; plan_id: string; status: string;
  expires_at: string | null; payment_order_id: number | null; created_at: string | null;
};

type Plan = { plan_id: string; name: string; price_usdt: number; duration_days: number; trial?: boolean; enabled?: boolean };

const STATUS_LABEL: Record<string, string> = { active: "生效中", expired: "已过期", pending: "待支付" };

function statusBadge(status: string) {
  switch (status) {
    case "active": return <span className="badge badge-ok">生效中</span>;
    case "expired": return <span className="badge badge-muted">已过期</span>;
    default: return <span className="badge badge-warn">{STATUS_LABEL[status] || status}</span>;
  }
}

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 订阅管理：订阅列表 + 手动开通 + 编辑到期时间/状态 + 撤销。 */
export default function AdminSubscriptionsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const [items, setItems] = useState<Sub[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  // 手动开通弹窗
  const [openShow, setOpenShow] = useState(false);
  const [openForm, setOpenForm] = useState({ user_id: "", plan_id: "", duration_days: "" });
  // 编辑弹窗
  const [editTarget, setEditTarget] = useState<Sub | null>(null);
  const [editStatus, setEditStatus] = useState("active");
  const [editExpires, setEditExpires] = useState("");

  const PAGE_SIZE = 20;
  const planName = useCallback((pid: string) => plans.find((p) => p.plan_id === pid)?.name || pid, [plans]);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (status) params.set("status", status);
      if (keyword.trim()) params.set("keyword", keyword.trim());
      const r = await apiFetch<{ items: Sub[]; total: number }>(`/admin/v1/subscriptions?${params}`, {}, tokenStore.adminAccess);
      setItems(r.items);
      setTotal(r.total);
    } catch { /* ignore */ }
  }, [page, status, keyword]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
    apiFetch<{ plans: Plan[] }>("/admin/v1/settings/plans", {}, tokenStore.adminAccess).then((r) => setPlans(r.plans)).catch(() => {});
  }, [load, router]);

  async function doOpen() {
    const uid = Number(openForm.user_id);
    if (!uid || uid <= 0) { toast("warn", "请填写用户 ID"); return; }
    if (!openForm.plan_id) { toast("warn", "请选择套餐"); return; }
    try {
      const body: Record<string, unknown> = { user_id: uid, plan_id: openForm.plan_id };
      const days = Number(openForm.duration_days);
      if (openForm.duration_days && days > 0) body.duration_days = days;
      const r = await apiFetch<Sub>("/admin/v1/subscriptions", { method: "POST", body: JSON.stringify(body) }, tokenStore.adminAccess);
      toast("success", `已为 ${r.email || `#${uid}`} 开通 ${planName(r.plan_id)}（至 ${fmtTime(r.expires_at)}）`);
      setOpenShow(false);
      setOpenForm({ user_id: "", plan_id: "", duration_days: "" });
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "开通失败");
    }
  }

  async function doEdit() {
    if (!editTarget) return;
    try {
      const body: Record<string, unknown> = {};
      if (editStatus !== editTarget.status) body.status = editStatus;
      const exp = new Date(editExpires);
      if (!isNaN(exp.getTime())) body.expires_at = exp.toISOString();
      if (Object.keys(body).length === 0) { toast("warn", "没有修改"); return; }
      await apiFetch(`/admin/v1/subscriptions/${editTarget.id}`, { method: "PATCH", body: JSON.stringify(body) }, tokenStore.adminAccess);
      toast("success", `订阅 #${editTarget.id} 已更新`);
      setEditTarget(null);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "更新失败");
    }
  }

  async function doDelete(s: Sub) {
    const ok = await confirm({
      title: "撤销订阅",
      message: `撤销 ${s.email || `#${s.user_id}`} 的 ${planName(s.plan_id)} 订阅？\n删除后该用户将失去订阅权限。`,
      danger: true,
      confirmText: "撤销",
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/subscriptions/${s.id}`, { method: "DELETE" }, tokenStore.adminAccess);
      toast("success", `订阅 #${s.id} 已撤销`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "撤销失败");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
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
          <div className="page-eyebrow">SUBSCRIPTION MANAGEMENT</div>
          <h1 className="page-title">
            订阅管理<small>{total.toLocaleString()} 条订阅</small>
          </h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={() => { setOpenForm({ user_id: "", plan_id: plans[0]?.plan_id || "", duration_days: "" }); setOpenShow(true); }}>手动开通</button>
        </div>
      </div>

      {/* 筛选栏 */}
      <div
        style={{
          display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
          padding: "12px 16px", background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 8, marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>筛选</span>
        <input className="input" style={{ width: 220 }} placeholder="搜索用户邮箱…" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(1); }} />
        <select className="input" style={{ width: 140 }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">全部状态</option>
          <option value="active">生效中</option>
          <option value="expired">已过期</option>
          <option value="pending">待支付</option>
        </select>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
          共 {total.toLocaleString()} 条
        </span>
      </div>

      {/* 订阅列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>订阅列表</div>
          <span className="panel-sub">/admin/v1/subscriptions · 手动开通/编辑/撤销均强制审计留痕</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>用户</th>
                <th>套餐</th>
                <th>状态</th>
                <th>到期时间</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无订阅记录</td></tr>
              )}
              {items.map((s) => (
                <tr key={s.id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>#{s.id}</td>
                  <td>
                    <div>{s.email || "—"}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>UID {s.user_id}</div>
                  </td>
                  <td>{planName(s.plan_id)}<div style={{ fontSize: 11, color: "var(--muted)" }}>{s.plan_id}</div></td>
                  <td>{statusBadge(s.status)}</td>
                  <td className="sub-ref">{fmtTime(s.expires_at)}</td>
                  <td className="sub-ref">{fmtTime(s.created_at)}</td>
                  <td>
                    <button className="action-link" onClick={() => { setEditTarget(s); setEditStatus(s.status); setEditExpires(s.expires_at ? new Date(s.expires_at).toISOString().slice(0, 16) : ""); }}>编辑</button>
                    {" · "}
                    <button className="action-link danger" onClick={() => doDelete(s)}>撤销</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 16 }}>
            <button style={pageBtn(false)} disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).slice(0, 7).map((p) => (
              <button key={p} style={pageBtn(page === p)} onClick={() => setPage(p)}>{p}</button>
            ))}
            <button style={pageBtn(false)} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>›</button>
          </div>
        )}
      </div>

      {/* 手动开通弹窗 */}
      {openShow && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">手动开通订阅</div>
              <button className="modal-close" onClick={() => setOpenShow(false)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>绕过支付流程直接为用户开通订阅（旧订阅自动过期）。</div>
            <div className="field">
              <label className="field-label">用户 ID</label>
              <input className="input" type="number" min={1} placeholder="用户 ID（可在用户管理查看）" value={openForm.user_id} onChange={(e) => setOpenForm({ ...openForm, user_id: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">套餐</label>
              <select className="input" value={openForm.plan_id} onChange={(e) => setOpenForm({ ...openForm, plan_id: e.target.value })}>
                {plans.length === 0 && <option value="">暂无套餐（请先在系统设置添加）</option>}
                {plans.map((p) => (
                  <option key={p.plan_id} value={p.plan_id}>{p.name}（{p.price_usdt}U / {p.duration_days}天）</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label">时长（天，留空用套餐默认）</label>
              <input className="input" type="number" min={1} placeholder="如 30" value={openForm.duration_days} onChange={(e) => setOpenForm({ ...openForm, duration_days: e.target.value })} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setOpenShow(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={doOpen}>开通</button>
            </div>
          </div>
        </div>
      )}

      {/* 编辑弹窗 */}
      {editTarget && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">编辑订阅 #{editTarget.id}</div>
              <button className="modal-close" onClick={() => setEditTarget(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              {editTarget.email || `UID ${editTarget.user_id}`} · {planName(editTarget.plan_id)}
            </div>
            <div className="field">
              <label className="field-label">状态</label>
              <select className="input" value={editStatus} onChange={(e) => setEditStatus(e.target.value)}>
                <option value="active">生效中</option>
                <option value="expired">已过期</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">到期时间</label>
              <input className="input" type="datetime-local" value={editExpires} onChange={(e) => setEditExpires(e.target.value)} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditTarget(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={doEdit}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
