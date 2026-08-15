"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type UserRow = { id: number; email: string; role: string; is_active: boolean; is_frozen: boolean; created_at: string | null };

/** M5 T5.2 用户管理：列表 + 搜索 + 冻结/解冻。 */
export default function AdminUsersPage() {
  const router = useRouter();
  const [items, setItems] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async (query = "") => {
    try {
      const r = await apiFetch<{ items: UserRow[]; total: number }>(`/admin/v1/users?q=${encodeURIComponent(query)}&size=50`, {}, tokenStore.adminAccess);
      setItems(r.items);
      setTotal(r.total);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function toggleFreeze(u: UserRow) {
    try {
      await apiFetch(`/admin/v1/users/${u.id}/freeze`, { method: "PATCH", body: JSON.stringify({ frozen: !u.is_frozen }) }, tokenStore.adminAccess);
      setMsg(`用户 ${u.email} 已${u.is_frozen ? "解冻" : "冻结"}`);
      load(q);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>用户管理（{total}）</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <input className="input" style={{ width: 280 }} placeholder="邮箱搜索" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-secondary" onClick={() => load(q)}>搜索</button>
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>邮箱</th><th style={th}>角色</th><th style={th}>状态</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>{u.id}</td>
                <td style={{ ...td, fontWeight: 600 }}>{u.email}</td>
                <td style={td}>{u.role}</td>
                <td style={td}>
                  {u.is_frozen ? <span style={{ color: "var(--danger)" }}>已冻结</span> : u.is_active ? <span style={{ color: "var(--success)" }}>正常</span> : <span style={{ color: "var(--muted)" }}>未激活</span>}
                </td>
                <td style={td}>
                  <button className="btn btn-secondary" style={{ padding: "5px 12px", fontSize: 12 }} onClick={() => toggleFreeze(u)}>
                    {u.is_frozen ? "解冻" : "冻结"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
