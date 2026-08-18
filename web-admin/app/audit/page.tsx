"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Audit = {
  id: number; actor_id: number; action: string; target_type: string; target_id: string;
  before: string | null; after: string | null; reason: string | null; ip: string | null; created_at: string;
};

const ACT_LABEL: Record<string, string> = {
  payment_manual_confirm: "强制确认支付", payment_manual_fail: "支付标记失败",
  withdrawal_approve: "通过提现", withdrawal_reject: "驳回提现", withdrawal_fill_tx: "填写 TxHash", withdrawal_retry: "重试发放", withdrawal_refund: "退还申请",
  strategy_list: "信号源上架", strategy_force_list: "强制上架信号源", strategy_pause: "暂停策略", strategy_delist: "下架策略",
  user_freeze: "冻结用户", user_unfreeze: "解冻用户",
  reward_manual_grant: "手动补发奖励", reward_manual_deduct: "手动扣除奖励",
  risk_rule_update: "更新风控参数", risk_emergency: "紧急制动",
  "exchange_invite.create": "新增邀请码", "exchange_invite.status": "启停邀请码", "exchange_invite.delete": "删除邀请码",
  review_approve: "通过主号审核", review_reject: "驳回主号审核",
};

function classify(action: string): { tag: string; label: string } {
  if (/manual_confirm|emergency|freeze|delete|force_list|deduct/.test(action)) return { tag: "danger", label: "高危" };
  if (/create|list|grant|approve/.test(action)) return { tag: "create", label: "创建" };
  if (/status|reject|pause|delist|unfreeze|fill_tx|retry|refund|rule_update/.test(action)) return { tag: "update", label: "更新" };
  if (/query|search|get|read/.test(action)) return { tag: "query", label: "查询" };
  return { tag: "update", label: "更新" };
}

/** M5 T5.7 审计日志（对齐演示稿 audit：筛选栏 + 类型标签 + 操作内容高亮 + 分页）。 */
export default function AdminAuditPage() {
  const router = useRouter();
  const [items, setItems] = useState<Audit[]>([]);
  const [total, setTotal] = useState(0);
  const [actor, setActor] = useState("");
  const [type, setType] = useState("全部");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const load = useCallback(async (p = 1) => {
    try {
      const qs = new URLSearchParams({ size: String(PAGE_SIZE), page: String(p) });
      const r = await apiFetch<{ items: Audit[]; total: number }>(`/admin/v1/audit?${qs.toString()}`, {}, tokenStore.adminAccess);
      setItems(r.items);
      setTotal(r.total);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  const filtered = useMemo(() => {
    return items.filter((e) => {
      if (actor && !String(e.actor_id).includes(actor.trim())) return false;
      if (type !== "全部" && classify(e.action).label !== type) return false;
      return true;
    });
  }, [items, actor, type]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function contentLine(e: Audit): React.ReactNode {
    const label = ACT_LABEL[e.action] || e.action;
    const parts: React.ReactNode[] = [<span key="l" style={{ color: "var(--fg)" }}>{label}</span>];
    if (e.target_id) parts.push(<span key="t" style={{ color: "var(--accent)", fontFamily: "var(--font-geist-mono), monospace" }}> #{e.target_type || "obj"}:{e.target_id}</span>);
    if (e.reason) parts.push(<span key="r" style={{ color: "var(--muted)" }}> · 原因：{e.reason}</span>);
    if (e.before || e.after) {
      parts.push(<span key="c" style={{ color: "var(--muted)" }}> · 变更：</span>);
      parts.push(<span key="b" style={{ color: "#f87171", fontFamily: "var(--font-geist-mono), monospace", fontSize: 11 }}>{e.before || "—"} → {e.after || "—"}</span>);
    }
    return <>{parts}</>;
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">AUDIT LOG · 审计日志</div>
          <h1 className="page-title">审计日志<small>写操作全量留痕 · 不可删除</small></h1>
        </div>
      </div>

      {/* 筛选栏 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>操作者</span>
        <input className="input" style={{ width: 140, height: 32 }} placeholder="admin01 / reviewer02…" value={actor} onChange={(e) => setActor(e.target.value)} />
        <span style={{ fontSize: 12, color: "var(--muted)" }}>操作类型</span>
        <select className="select" style={{ width: 140, height: 32 }} value={type} onChange={(e) => setType(e.target.value)}>
          <option>全部</option><option>创建</option><option>更新</option><option>高危</option><option>查询</option>
        </select>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono), monospace" }}>共 {total.toLocaleString()} 条</span>
      </div>

      {/* 日志列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>审计记录</div>
          <span className="panel-sub">操作人 · 时间 · 目标 · 变更前后 · IP · 不可删除</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>时间</th><th>操作者</th><th>类型</th><th>操作内容</th><th>IP</th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无审计记录</td></tr>}
              {filtered.map((e) => {
                const t = e.created_at ? new Date(e.created_at) : null;
                const time = t ? `${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")} ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}` : "—";
                const cls = classify(e.action);
                const tagColor = cls.tag === "danger" ? "#f87171" : cls.tag === "create" ? "#28c464" : cls.tag === "query" ? "#60a5fa" : "#facc15";
                return (
                  <tr key={e.id}>
                    <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11, color: "var(--text-tertiary, #64748b)" }}>{time}</td>
                    <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11, color: "var(--muted)" }}>admin{e.actor_id}</td>
                    <td><span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, border: "1px solid", color: tagColor, borderColor: tagColor + "66", background: tagColor + "14" }}>{cls.label}</span></td>
                    <td className="sub-ref" style={{ whiteSpace: "normal", minWidth: 360 }}>{contentLine(e)}</td>
                    <td style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11, color: "var(--muted)" }}>{e.ip || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* 分页 */}
        {totalPages > 1 && (
          <div style={{ display: "flex", gap: 6, marginTop: 16, alignItems: "center", justifyContent: "flex-end" }}>
            <button className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => { setPage(page - 1); load(page - 1); }}>‹</button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              let p = i + 1;
              if (totalPages > 5 && page > 3) p = page - 3 + i;
              if (p > totalPages) p = totalPages;
              return (
                <button key={p} className={`btn btn-sm${p === page ? " btn-primary" : " btn-secondary"}`} onClick={() => { setPage(p); load(p); }}>{p}</button>
              );
            })}
            <button className="btn btn-secondary btn-sm" disabled={page >= totalPages} onClick={() => { setPage(page + 1); load(page + 1); }}>›</button>
          </div>
        )}
      </div>
    </div>
  );
}
