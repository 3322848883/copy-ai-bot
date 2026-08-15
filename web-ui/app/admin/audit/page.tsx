"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Audit = { id: number; actor_id: number; action: string; target_type: string; target_id: string; before: string | null; after: string | null; reason: string | null; ip: string | null; created_at: string };

/** M5 T5.7 审计日志：查询 + 详情（写操作全量留痕）。 */
export default function AdminAuditPage() {
  const router = useRouter();
  const [items, setItems] = useState<Audit[]>([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async (a = action) => {
    try {
      // ★ 修复：无过滤时须用 ? 而非 & 开头，否则路径变 /admin/v1/audit&size=50 → 404
      const qs = new URLSearchParams({ size: "50" });
      if (a) qs.set("action", a);
      const r = await apiFetch<{ items: Audit[]; total: number }>(`/admin/v1/audit?${qs.toString()}`, {}, tokenStore.adminAccess);
      setItems(r.items);
      setTotal(r.total);
    } catch { /* ignore */ }
  }, [action]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>审计日志（{total}）</div>
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <input className="input" style={{ width: 280 }} placeholder="按 action 过滤（如 withdrawal.approve）" value={action} onChange={(e) => setAction(e.target.value)} />
        <button className="btn btn-secondary" onClick={() => load()}>过滤</button>
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>操作者</th><th style={th}>动作</th><th style={th}>对象</th><th style={th}>时间</th><th style={th}>详情</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <>
                <tr key={e.id} style={{ borderTop: "1px solid var(--rule)", cursor: "pointer" }} onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                  <td style={td}>{e.id}</td>
                  <td style={td}>#{e.actor_id}</td>
                  <td style={{ ...td, fontFamily: "monospace", color: "var(--accent)" }}>{e.action}</td>
                  <td style={td}>{e.target_type}:{e.target_id}</td>
                  <td style={{ ...td, color: "var(--muted)", fontSize: 12 }}>{e.created_at?.replace("T", " ").slice(0, 19)}</td>
                  <td style={{ ...td, color: "var(--muted)" }}>{expanded === e.id ? "收起 ▲" : "展开 ▼"}</td>
                </tr>
                {expanded === e.id && (
                  <tr key={`d-${e.id}`} style={{ borderTop: "1px solid var(--rule)", background: "rgba(255,255,255,.02)" }}>
                    <td colSpan={6} style={{ ...td, whiteSpace: "pre-wrap", fontSize: 12, color: "var(--muted)" }}>
                      <div><b>before:</b> {e.before || "—"}</div>
                      <div><b>after:</b> {e.after || "—"}</div>
                      <div><b>reason:</b> {e.reason || "—"}</div>
                      <div><b>ip:</b> {e.ip || "—"}</div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {items.length === 0 && <tr><td colSpan={6} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无审计记录</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
