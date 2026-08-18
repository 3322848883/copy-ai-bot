"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Announcement = {
  id: number;
  title: string;
  body: string | null;
  level: string; // info / warning / critical
  status: string; // draft / published / offline
  pinned: boolean;
  published_at?: string | null;
  created_at?: string | null;
};

const STATUS_TABS = ["全部", "published", "draft", "offline"];
const STATUS_LABEL: Record<string, string> = { published: "已发布", draft: "草稿", offline: "已下线" };
const LEVEL_LABEL: Record<string, string> = { info: "常规", warning: "重要", critical: "紧急" };

const emptyForm = { title: "", body: "", level: "info", pinned: false };

/** 公告管理：列表 + 新增/编辑弹窗 + 发布/下线/删除，全部审计留痕，发布时 WS 全站广播。 */
export default function AdminAnnouncementsPage() {
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<Announcement[]>([]);
  const [tab, setTab] = useState("全部");

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const q = tab === "全部" ? "" : `?status=${tab}`;
      const r = await apiFetch<{ items: Announcement[] }>(`/admin/v1/announcements${q}`, {}, tokenStore.adminAccess);
      setItems(r.items);
    } catch { /* ignore */ }
  }, [tab]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  function openCreate() {
    setEditId(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function openEdit(a: Announcement) {
    setEditId(a.id);
    setForm({ title: a.title, body: a.body ?? "", level: a.level, pinned: a.pinned });
    setShowForm(true);
  }

  async function submit() {
    if (!form.title.trim()) {
      toast("warn", "请填写公告标题");
      return;
    }
    setBusy(true);
    try {
      const body = JSON.stringify({
        title: form.title.trim(),
        body: form.body.trim() || null,
        level: form.level,
        pinned: form.pinned,
      });
      if (editId === null) {
        await apiFetch("/admin/v1/announcements", { method: "POST", body }, tokenStore.adminAccess);
        toast("success", "已创建草稿，发布后用户可见");
      } else {
        await apiFetch(`/admin/v1/announcements/${editId}`, { method: "PATCH", body }, tokenStore.adminAccess);
        toast("success", "公告已保存");
      }
      setShowForm(false);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(a: Announcement, status: string) {
    try {
      await apiFetch(`/admin/v1/announcements/${a.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }, tokenStore.adminAccess);
      if (status === "published") toast("success", `已发布「${a.title}」 · 全站 WS 广播`);
      else if (status === "offline") toast("warn", `已下线「${a.title}」`);
      else toast("success", "已转回草稿");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function remove(a: Announcement) {
    if (!window.confirm(`确认删除公告「${a.title}」？删除后不可恢复。`)) return;
    try {
      await apiFetch(`/admin/v1/announcements/${a.id}`, { method: "DELETE" }, tokenStore.adminAccess);
      toast("success", "已删除 · 审计留痕");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "删除失败");
    }
  }

  function togglePin(a: Announcement) {
    // 置顶仅对已发布公告有意义，直接走编辑接口
    apiFetch(
      `/admin/v1/announcements/${a.id}`,
      { method: "PATCH", body: JSON.stringify({ title: a.title, body: a.body, level: a.level, pinned: !a.pinned }) },
      tokenStore.adminAccess,
    )
      .then(() => {
        toast("success", a.pinned ? "已取消置顶" : "已置顶，前台将排在最前");
        load();
      })
      .catch((e: unknown) => toast("error", e instanceof Error ? e.message : "操作失败"));
  }

  return (
    <div>
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">ANNOUNCEMENTS · 平台公告</div>
          <h1 className="page-title">公告管理<small>草稿 → 发布 → 下线 · 发布即 WS 广播</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={openCreate}>＋ 新建公告</button>
        </div>
      </div>

      <div className="ex-tabs">
        {STATUS_TABS.map((t) => (
          <button key={t} className={`ex-tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {t === "全部" ? "全部" : STATUS_LABEL[t]}
          </button>
        ))}
      </div>

      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>公告列表</div>
          <span className="panel-sub">/admin/v1/announcements · 前台横幅 + 铃铛消息可见已发布公告</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>标题</th><th>级别</th><th>状态</th><th className="num">置顶</th><th>发布时间</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)" }}>暂无公告</td></tr>}
              {items.map((a) => (
                <tr key={a.id}>
                  <td style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.body ?? undefined}>
                    {a.title}
                  </td>
                  <td>
                    <span
                      className="badge"
                      style={{
                        fontSize: 10,
                        padding: "2px 8px",
                        borderRadius: 2,
                        color: a.level === "critical" ? "#f87171" : a.level === "warning" ? "var(--warning, #eab308)" : "#00d4aa",
                        border: `1px solid ${a.level === "critical" ? "rgba(248,113,113,0.4)" : a.level === "warning" ? "rgba(234,179,8,0.4)" : "rgba(0,212,170,0.4)"}`,
                      }}
                    >
                      {LEVEL_LABEL[a.level] ?? a.level}
                    </span>
                  </td>
                  <td>
                    {a.status === "published" ? <span className="badge badge-ok">已发布</span> : a.status === "draft" ? <span className="badge badge-muted">草稿</span> : <span className="badge badge-err">已下线</span>}
                  </td>
                  <td className="num">
                    <button className="btn btn-secondary btn-sm" style={{ padding: "2px 10px" }} onClick={() => togglePin(a)} disabled={a.status !== "published"}>
                      {a.pinned ? "★ 已置顶" : "☆ 置顶"}
                    </button>
                  </td>
                  <td className="sub-ref">{a.published_at ? new Date(a.published_at).toLocaleString("zh-CN", { hour12: false }) : "—"}</td>
                  <td className="sub-ref">{a.created_at ? new Date(a.created_at).toLocaleString("zh-CN", { hour12: false }) : "—"}</td>
                  <td>
                    {a.status === "published" ? (
                      <button className="btn btn-secondary btn-sm" style={{ marginRight: 6 }} onClick={() => setStatus(a, "offline")}>下线</button>
                    ) : (
                      <button className="btn btn-primary btn-sm" style={{ marginRight: 6 }} onClick={() => setStatus(a, "published")}>发布</button>
                    )}
                    <button className="btn btn-secondary btn-sm" style={{ marginRight: 6 }} onClick={() => openEdit(a)}>编辑</button>
                    <button className="btn btn-secondary btn-sm" style={{ color: "#f87171" }} onClick={() => remove(a)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 4, background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.25)", fontSize: 12, color: "var(--warning)" }}>
          ℹ 公告级别仅影响前台横幅样式与排序（置顶 &gt; 发布时间）；发布动作将向全部在线用户 WS 广播 announcement.new，并写入审计日志。
        </div>
      </div>

      {showForm && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">{editId === null ? "新建公告" : `编辑公告 #${editId}`}</div>
              <button className="modal-close" onClick={() => setShowForm(false)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">标题（1-128 字）</label>
              <input className="input" placeholder="如：系统升级维护通知" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={128} />
            </div>
            <div className="field">
              <label className="field-label">正文（可选，前台横幅与铃铛详情展示）</label>
              <textarea className="input" style={{ minHeight: 120, resize: "vertical" }} placeholder="公告正文…" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} maxLength={8000} />
            </div>
            <div className="field">
              <label className="field-label">级别</label>
              <select className="select" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
                <option value="info">常规（青色横幅）</option>
                <option value="warning">重要（黄色横幅）</option>
                <option value="critical">紧急（红色横幅）</option>
              </select>
            </div>
            <div className="field" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input id="ann-pin" type="checkbox" checked={form.pinned} onChange={(e) => setForm({ ...form, pinned: e.target.checked })} />
              <label htmlFor="ann-pin" className="field-label" style={{ margin: 0 }}>置顶（已发布时前台排在最前）</label>
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>新建公告默认为草稿状态，用户不可见；点击「发布」后才在前台横幅与铃铛消息中出现，所有操作写 audit-log</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowForm(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={submit} disabled={busy || !form.title.trim()}>{busy ? "保存中…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
