"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Pending = { user_id: number; email: string; invite_code: string; selected_exchange: string; pool_exchange: string; pool_label: string; matched: boolean };
type Done = { id: number; action: string; target_id: string; actor_id: number; reason: string | null; created_at: string | null };

/** M5 主号下级审核：平台池码命中但所不匹配的异常申请，人工复核标记 sub_account（免订阅）。 */
export default function AdminReviewPage() {
  const router = useRouter();
  const [pending, setPending] = useState<Pending[]>([]);
  const [done, setDone] = useState<Done[]>([]);
  const [msg, setMsg] = useState("");
  const [remark, setRemark] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const [p, d] = await Promise.all([
        apiFetch<{ items: Pending[] }>("/admin/v1/review/pending", {}, tokenStore.adminAccess),
        apiFetch<{ items: Done[] }>("/admin/v1/review/done", {}, tokenStore.adminAccess),
      ]);
      setPending(p.items);
      setDone(d.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function act(u: Pending, action: "approve" | "reject") {
    try {
      await apiFetch(`/admin/v1/review/${u.user_id}/${action}`, { method: "POST", body: JSON.stringify({ remark: remark[u.user_id] || "" }) }, tokenStore.adminAccess);
      setMsg(`用户 ${u.email} 已${action === "approve" ? "通过（标记主号下级·免订阅）" : "驳回"}`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>主号下级审核</div>
      <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>平台池码命中 · 免订阅标记 · approve/reject + audit-log（G06）</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>待审核申请（{pending.length}）</div>
        {pending.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>暂无待审核申请</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                <th style={th}>申请用户</th><th style={th}>邀请码</th><th style={th}>所选所</th><th style={th}>池码所属</th><th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((u) => (
                <tr key={u.user_id} style={{ borderTop: "1px solid var(--rule)" }}>
                  <td style={td}>{u.email}</td>
                  <td style={{ ...td, fontFamily: "monospace" }}>{u.invite_code}</td>
                  <td style={td}>{u.selected_exchange || "-"}</td>
                  <td style={td}>
                    <span style={{ color: u.matched ? "var(--success)" : "var(--warning)" }}>{u.pool_exchange}{u.pool_label ? ` · ${u.pool_label}` : ""}</span>
                  </td>
                  <td style={td}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <button className="btn btn-primary" style={{ padding: "4px 12px", fontSize: 12 }} onClick={() => act(u, "approve")}>通过</button>
                      <button className="btn btn-secondary" style={{ padding: "4px 12px", fontSize: 12 }} onClick={() => act(u, "reject")}>驳回</button>
                      <input className="input" style={{ width: 140, padding: "4px 8px", fontSize: 12 }} placeholder="备注" value={remark[u.user_id] || ""} onChange={(e) => setRemark({ ...remark, [u.user_id]: e.target.value })} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 12 }}>已处理记录</div>
        {done.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>暂无处理记录</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                <th style={th}>用户</th><th style={th}>处理结果</th><th style={th}>处理人</th><th style={th}>时间</th><th style={th}>备注</th>
              </tr>
            </thead>
            <tbody>
              {done.map((d) => (
                <tr key={d.id} style={{ borderTop: "1px solid var(--rule)" }}>
                  <td style={td}>#{d.target_id}</td>
                  <td style={td}>
                    <span style={{ color: d.action === "review.approve" ? "var(--success)" : "var(--danger)" }}>{d.action === "review.approve" ? "已通过" : "已驳回"}</span>
                  </td>
                  <td style={td}>#{d.actor_id}</td>
                  <td style={td}>{d.created_at?.slice(0, 16) || "-"}</td>
                  <td style={{ ...td, color: "var(--muted)" }}>{d.reason || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };