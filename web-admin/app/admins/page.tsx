"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type AdminRow = {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  is_frozen: boolean;
  admin_note: string | null;
  is_self: boolean;
  created_at: string | null;
};

const ROLE_LABEL: Record<string, string> = { admin: "管理员", reviewer: "审核员", support: "客服" };
const ROLE_DESC: Record<string, string> = {
  admin: "全部后台权限（含管理员管理）",
  reviewer: "审核类操作（主号/信号源）",
  support: "查询与客服类操作",
};
const PASSWORD_MIN = 12;

const emptyCreate = { email: "", password: "", role: "admin", admin_note: "" };
const emptySelfPwd = { old_password: "", new_password: "", confirm: "" };

/** 管理员管理：后台账户的创建/编辑/角色调整/冻结/重置密码，全程审计留痕；
 *  改密或降权后目标账户旧令牌立即作废（须重新登录）。 */
export default function AdminAdminsPage() {
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<AdminRow[]>([]);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(emptyCreate);
  const [busy, setBusy] = useState(false);

  const [editRow, setEditRow] = useState<AdminRow | null>(null);
  const [editForm, setEditForm] = useState({ email: "", role: "admin", admin_note: "" });

  const [pwdRow, setPwdRow] = useState<AdminRow | null>(null);
  const [pwdForm, setPwdForm] = useState({ new_password: "", confirm: "" });

  const [showSelfPwd, setShowSelfPwd] = useState(false);
  const [selfPwd, setSelfPwd] = useState(emptySelfPwd);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: AdminRow[] }>("/admin/v1/admins", {}, tokenStore.adminAccess);
      setItems(r.items);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  function openCreate() {
    setCreateForm(emptyCreate);
    setShowCreate(true);
  }

  async function submitCreate() {
    if (!createForm.email.trim() || createForm.password.length < PASSWORD_MIN) {
      toast("warn", `请填写邮箱，密码至少 ${PASSWORD_MIN} 位`);
      return;
    }
    setBusy(true);
    try {
      await apiFetch(
        "/admin/v1/admins",
        {
          method: "POST",
          body: JSON.stringify({
            email: createForm.email.trim(),
            password: createForm.password,
            role: createForm.role,
            admin_note: createForm.admin_note.trim() || null,
          }),
        },
        tokenStore.adminAccess,
      );
      toast("success", "后台账户已创建 · 审计留痕");
      setShowCreate(false);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  function openEdit(a: AdminRow) {
    setEditRow(a);
    setEditForm({ email: a.email, role: a.role, admin_note: a.admin_note ?? "" });
  }

  async function submitEdit() {
    if (!editRow) return;
    setBusy(true);
    try {
      await apiFetch(
        `/admin/v1/admins/${editRow.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            email: editForm.email.trim(),
            role: editForm.role,
            admin_note: editForm.admin_note.trim() || null,
          }),
        },
        tokenStore.adminAccess,
      );
      toast("success", "已保存 · 审计留痕");
      setEditRow(null);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  function openResetPwd(a: AdminRow) {
    setPwdRow(a);
    setPwdForm({ new_password: "", confirm: "" });
  }

  async function submitResetPwd() {
    if (!pwdRow) return;
    if (pwdForm.new_password.length < PASSWORD_MIN) {
      toast("warn", `新密码至少 ${PASSWORD_MIN} 位`);
      return;
    }
    if (pwdForm.new_password !== pwdForm.confirm) {
      toast("warn", "两次输入的密码不一致");
      return;
    }
    setBusy(true);
    try {
      await apiFetch(
        `/admin/v1/admins/${pwdRow.id}/password`,
        { method: "PATCH", body: JSON.stringify({ new_password: pwdForm.new_password }) },
        tokenStore.adminAccess,
      );
      toast("success", `已重置 ${pwdRow.email} 的密码 · 其现有登录全部失效`);
      setPwdRow(null);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "重置失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFreeze(a: AdminRow) {
    if (a.is_self) return;
    const verb = a.is_frozen ? "解冻" : "冻结";
    if (!window.confirm(`确认${verb}「${a.email}」？${a.is_frozen ? "" : "冻结后该账户立即无法登录后台。"}`)) return;
    try {
      await apiFetch(
        `/admin/v1/admins/${a.id}/freeze`,
        { method: "PATCH", body: JSON.stringify({ frozen: !a.is_frozen }) },
        tokenStore.adminAccess,
      );
      toast("success", `已${verb} · 审计留痕`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function submitSelfPwd() {
    if (selfPwd.new_password.length < PASSWORD_MIN) {
      toast("warn", `新密码至少 ${PASSWORD_MIN} 位`);
      return;
    }
    if (selfPwd.new_password !== selfPwd.confirm) {
      toast("warn", "两次输入的新密码不一致");
      return;
    }
    setBusy(true);
    try {
      await apiFetch(
        "/admin/v1/admins/me/password",
        { method: "PATCH", body: JSON.stringify({ old_password: selfPwd.old_password, new_password: selfPwd.new_password }) },
        tokenStore.adminAccess,
      );
      toast("success", "密码已修改，即将返回登录页重新登录");
      setShowSelfPwd(false);
      setSelfPwd(emptySelfPwd);
      setTimeout(() => {
        tokenStore.clearAdmin();
        router.push("/login");
      }, 1200);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "修改失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">ADMINS · 权限治理</div>
          <h1 className="page-title">管理员管理<small>后台账户增删改 · 角色分权 · 改密即吊销全部会话</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={() => setShowSelfPwd(true)}>修改我的密码</button>
          <button className="btn btn-primary" onClick={openCreate}>＋ 新增后台账户</button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>后台账户列表</div>
          <span className="panel-sub">/admin/v1/admins · 全部操作写入审计日志</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>ID</th><th>邮箱</th><th>角色</th><th>状态</th><th>备注</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)" }}>暂无后台账户</td></tr>}
              {items.map((a) => (
                <tr key={a.id}>
                  <td className="num">{a.id}</td>
                  <td>
                    {a.email}
                    {a.is_self && <span className="badge badge-info" style={{ marginLeft: 8 }}>我</span>}
                  </td>
                  <td>
                    <span className={a.role === "admin" ? "badge badge-err" : a.role === "reviewer" ? "badge badge-info" : "badge badge-muted"}>
                      {ROLE_LABEL[a.role] ?? a.role}
                    </span>
                  </td>
                  <td>
                    {a.is_frozen ? <span className="badge badge-err">已冻结</span> : a.is_active ? <span className="badge badge-ok">正常</span> : <span className="badge badge-muted">已停用</span>}
                  </td>
                  <td style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.admin_note ?? undefined}>
                    {a.admin_note ?? "—"}
                  </td>
                  <td className="sub-ref">{a.created_at ? new Date(a.created_at).toLocaleString("zh-CN", { hour12: false }) : "—"}</td>
                  <td>
                    <button className="btn btn-secondary btn-sm" style={{ marginRight: 6 }} onClick={() => openEdit(a)}>编辑</button>
                    <button className="btn btn-secondary btn-sm" style={{ marginRight: 6 }} onClick={() => openResetPwd(a)}>重置密码</button>
                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ color: a.is_frozen ? undefined : "#f87171" }}
                      onClick={() => toggleFreeze(a)}
                      disabled={a.is_self}
                      title={a.is_self ? "不能冻结自己的账户" : undefined}
                    >
                      {a.is_frozen ? "解冻" : "冻结"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 4, background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.25)", fontSize: 12, color: "var(--warning)" }}>
          ℹ 安全规则：密码至少 12 位；重置密码或调整角色后目标账户全部登录即刻失效；系统始终保留至少一个可用管理员，防止后台锁死；不能冻结自己或修改自己的角色。
        </div>
      </div>

      {showCreate && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setShowCreate(false); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">新增后台账户</div>
              <button className="modal-close" onClick={() => setShowCreate(false)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">邮箱（登录账号）</label>
              <input className="input" placeholder="admin@example.com" value={createForm.email} onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} maxLength={255} />
            </div>
            <div className="field">
              <label className="field-label">初始密码（至少 {PASSWORD_MIN} 位）</label>
              <input className="input" type="password" placeholder={`≥ ${PASSWORD_MIN} 位`} value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">角色</label>
              <select className="select" value={createForm.role} onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}>
                <option value="admin">管理员 — {ROLE_DESC.admin}</option>
                <option value="reviewer">审核员 — {ROLE_DESC.reviewer}</option>
                <option value="support">客服 — {ROLE_DESC.support}</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">备注（可选）</label>
              <input className="input" placeholder="如：运营负责人" value={createForm.admin_note} onChange={(e) => setCreateForm({ ...createForm, admin_note: e.target.value })} maxLength={2000} />
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>初始密码仅此处设置一次，创建后请通过「重置密码」修改；账户创建即刻可登录后台（无邮箱验证环节）</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowCreate(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={submitCreate} disabled={busy}>{busy ? "创建中…" : "创建"}</button>
            </div>
          </div>
        </div>
      )}

      {editRow && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setEditRow(null); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">编辑后台账户 #{editRow.id}</div>
              <button className="modal-close" onClick={() => setEditRow(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">邮箱</label>
              <input className="input" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} maxLength={255} />
            </div>
            <div className="field">
              <label className="field-label">角色{editRow.is_self ? "（不能修改自己的角色）" : ""}</label>
              <select className="select" value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })} disabled={editRow.is_self}>
                <option value="admin">管理员 — {ROLE_DESC.admin}</option>
                <option value="reviewer">审核员 — {ROLE_DESC.reviewer}</option>
                <option value="support">客服 — {ROLE_DESC.support}</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">备注（可选）</label>
              <input className="input" value={editForm.admin_note} onChange={(e) => setEditForm({ ...editForm, admin_note: e.target.value })} maxLength={2000} />
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>角色变更后该账户现有登录立即失效，需用新角色重新登录；降掉最后一个管理员会被系统拒绝</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditRow(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={submitEdit} disabled={busy}>{busy ? "保存中…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}

      {pwdRow && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setPwdRow(null); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">重置密码 · {pwdRow.email}</div>
              <button className="modal-close" onClick={() => setPwdRow(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">新密码（至少 {PASSWORD_MIN} 位）</label>
              <input className="input" type="password" placeholder={`≥ ${PASSWORD_MIN} 位`} value={pwdForm.new_password} onChange={(e) => setPwdForm({ ...pwdForm, new_password: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">确认新密码</label>
              <input className="input" type="password" placeholder="再次输入" value={pwdForm.confirm} onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })} />
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>重置后该账户全部现有登录立即失效（含当前在线会话），需用新密码重新登录</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setPwdRow(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={submitResetPwd} disabled={busy}>{busy ? "重置中…" : "确认重置"}</button>
            </div>
          </div>
        </div>
      )}

      {showSelfPwd && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setShowSelfPwd(false); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">修改我的密码</div>
              <button className="modal-close" onClick={() => setShowSelfPwd(false)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">原密码</label>
              <input className="input" type="password" placeholder="当前密码" value={selfPwd.old_password} onChange={(e) => setSelfPwd({ ...selfPwd, old_password: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">新密码（至少 {PASSWORD_MIN} 位）</label>
              <input className="input" type="password" placeholder={`≥ ${PASSWORD_MIN} 位`} value={selfPwd.new_password} onChange={(e) => setSelfPwd({ ...selfPwd, new_password: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">确认新密码</label>
              <input className="input" type="password" placeholder="再次输入" value={selfPwd.confirm} onChange={(e) => setSelfPwd({ ...selfPwd, confirm: e.target.value })} />
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>修改成功后当前登录会立即失效，需用新密码重新登录后台</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowSelfPwd(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={submitSelfPwd} disabled={busy}>{busy ? "提交中…" : "确认修改"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
