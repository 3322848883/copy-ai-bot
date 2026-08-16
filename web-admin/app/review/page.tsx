"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Pending = { user_id: number; email: string; invite_code: string; selected_exchange: string; pool_exchange: string; pool_label: string; matched: boolean };
type Done = { id: number; action: string; target_id: string; actor_id: number; reason: string | null; created_at: string | null };

/** M5 主号下级审核：平台池码命中但所不匹配的异常申请，人工复核标记 sub_account（免订阅）。 */
export default function AdminReviewPage() {
  const router = useRouter();
  const toast = useToast();
  const [pending, setPending] = useState<Pending[]>([]);
  const [done, setDone] = useState<Done[]>([]);
  const [remark, setRemark] = useState<Record<number, string>>({});
  const [q, setQ] = useState("");
  const [pFilter, setPFilter] = useState<"all" | "matched" | "unmatched">("all");
  const [dFilter, setDFilter] = useState<"all" | "approve" | "reject">("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, d] = await Promise.all([
        apiFetch<{ items: Pending[] }>("/admin/v1/review/pending", {}, tokenStore.adminAccess),
        apiFetch<{ items: Done[] }>("/admin/v1/review/done", {}, tokenStore.adminAccess),
      ]);
      setPending(p.items);
      setDone(d.items);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function act(u: Pending, action: "approve" | "reject") {
    try {
      await apiFetch(`/admin/v1/review/${u.user_id}/${action}`, { method: "POST", body: JSON.stringify({ remark: remark[u.user_id] || "" }) }, tokenStore.adminAccess);
      toast(action === "approve" ? "success" : "info", `用户 ${u.email} 已${action === "approve" ? "通过（标记主号下级·免订阅）" : "驳回"} · 已留审计日志`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  const pendFiltered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    let list = pending;
    if (pFilter === "matched") list = list.filter((u) => u.matched);
    if (pFilter === "unmatched") list = list.filter((u) => !u.matched);
    if (kw) {
      list = list.filter(
        (u) =>
          u.email.toLowerCase().includes(kw) ||
          u.invite_code.toLowerCase().includes(kw) ||
          u.selected_exchange.toLowerCase().includes(kw) ||
          u.pool_exchange.toLowerCase().includes(kw)
      );
    }
    return list;
  }, [pending, pFilter, q]);

  const doneFiltered = useMemo(() => {
    if (dFilter === "approve") return done.filter((d) => d.action === "review.approve");
    if (dFilter === "reject") return done.filter((d) => d.action === "review.reject");
    return done;
  }, [done, dFilter]);

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">MAIN ACCOUNT REVIEW</div>
          <h1 className="page-title">
            主号审核<small>平台池码命中 · 人工复核标记 sub_account · 免订阅（G06）</small>
          </h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={load} disabled={loading}>{loading ? "刷新中…" : "刷新"}</button>
        </div>
      </div>

      {/* 待办告警 */}
      {pending.length > 0 && (
        <div className="alert-strip">
          <span>⚠</span>
          <span>有 <strong>{pending.length}</strong> 条主号下级申请待人工复核（平台池码命中，所选所不匹配）</span>
        </div>
      )}

      {/* 待审核申请 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>待审核申请</div>
          <span className="panel-sub">/admin/v1/review/pending · {pending.length} 条待处理</span>
        </div>

        {/* 搜索 + 筛选 + 操作 */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
          <input
            className="input"
            style={{ width: 260 }}
            placeholder="搜索邮箱 / 邀请码 / 交易所"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8 }}>
            {([["all", "全部"], ["matched", "已匹配"], ["unmatched", "所不匹配"]] as const).map(([key, label]) => (
              <button
                key={key}
                className="btn"
                style={{
                  padding: "5px 14px", borderRadius: 999, height: "auto", minWidth: 0, fontSize: 12,
                  border: pFilter === key ? "1px solid var(--admin-red-border)" : "1px solid var(--rule)",
                  background: pFilter === key ? "rgba(239,68,68,0.1)" : "transparent",
                  color: pFilter === key ? "var(--admin-red)" : "var(--muted)",
                }}
                onClick={() => setPFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
            显示 {pendFiltered.length} / {pending.length} 条
          </span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>申请用户</th>
                <th>邀请码</th>
                <th>所选所</th>
                <th>池码所属</th>
                <th>匹配状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {pendFiltered.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)" }}>暂无待审核申请</td>
                </tr>
              )}
              {pendFiltered.map((u) => (
                <tr key={u.user_id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{u.email}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{u.invite_code}</td>
                  <td>{u.selected_exchange || "—"}</td>
                  <td>{u.pool_exchange}{u.pool_label ? ` · ${u.pool_label}` : ""}</td>
                  <td>
                    {u.matched ? (
                      <span className="badge badge-ok">已匹配</span>
                    ) : (
                      <span className="badge badge-warn">所不匹配</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <input
                        className="input"
                        style={{ width: 140, height: 28, padding: "0 8px", fontSize: 12 }}
                        placeholder="备注（留痕）"
                        value={remark[u.user_id] || ""}
                        onChange={(e) => setRemark({ ...remark, [u.user_id]: e.target.value })}
                      />
                      <button className="btn btn-primary btn-sm" onClick={() => act(u, "approve")}>通过</button>
                      <button className="btn btn-secondary btn-sm" onClick={() => act(u, "reject")}>驳回</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 已处理记录 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>已处理记录</div>
          <span className="panel-sub">/admin/v1/review/done · 最近 50 条</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {([["all", "全部"], ["approve", "已通过"], ["reject", "已驳回"]] as const).map(([key, label]) => (
            <button
              key={key}
              className="btn"
              style={{
                padding: "5px 14px", borderRadius: 999, height: "auto", minWidth: 0, fontSize: 12,
                border: dFilter === key ? "1px solid var(--admin-red-border)" : "1px solid var(--rule)",
                background: dFilter === key ? "rgba(239,68,68,0.1)" : "transparent",
                color: dFilter === key ? "var(--admin-red)" : "var(--muted)",
              }}
              onClick={() => setDFilter(key)}
            >
              {label}
            </button>
          ))}
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>
            共 {doneFiltered.length} 条
          </span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>处理结果</th>
                <th>处理人</th>
                <th>时间</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {doneFiltered.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>暂无处理记录</td>
                </tr>
              )}
              {doneFiltered.map((d) => (
                <tr key={d.id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>#{d.target_id}</td>
                  <td>
                    {d.action === "review.approve" ? (
                      <span className="badge badge-ok">已通过 · 主号下级</span>
                    ) : (
                      <span className="badge badge-err">已驳回</span>
                    )}
                  </td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>#{d.actor_id}</td>
                  <td className="sub-ref">{d.created_at?.slice(0, 16) || "—"}</td>
                  <td style={{ color: "var(--muted)", maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis" }}>{d.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
