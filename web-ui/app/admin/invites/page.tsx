"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Kpi = { today_count: number; today_amount_usdt: number; verifying_count: number; available_count: number; canceled_count: number; frozen_count: number };
type Abuse = { items: { inviter_id: number; email: string; bind_count: number }[]; threshold: number; window_hours: number };
type Relation = { id: number; inviter_email: string; code: string; invitee_id: number; trigger_amount_usdt: number; reward_usdt: number; status: string; status_label: string; verifying_ends_at: string | null; created_at: string | null };

/** M5 邀请奖励：10% 返佣看板 + 刷单告警（G11）+ 邀请关系列表。 */
export default function AdminInvitesPage() {
  const router = useRouter();
  const [kpi, setKpi] = useState<Kpi | null>(null);
  const [abuse, setAbuse] = useState<Abuse | null>(null);
  const [relations, setRelations] = useState<Relation[]>([]);

  const load = useCallback(async () => {
    try {
      const [k, a, r] = await Promise.all([
        apiFetch<Kpi>("/admin/v1/invites/kpi", {}, tokenStore.adminAccess),
        apiFetch<Abuse>("/admin/v1/invites/abuse", {}, tokenStore.adminAccess),
        apiFetch<{ items: Relation[] }>("/admin/v1/invites", {}, tokenStore.adminAccess),
      ]);
      setKpi(k);
      setAbuse(a);
      setRelations(r.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>邀请奖励</div>
      <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>10% 奖励 · 24h/48h 核实 · 风控看板</div>

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 16 }}>
        {[
          ["今日触发", `${kpi?.today_count ?? 0}`, `笔 · ${kpi?.today_amount_usdt ?? 0} USDT`],
          ["核实中", `${kpi?.verifying_count ?? 0}`, "笔 · 24h/48h"],
          ["已到账", `${kpi?.available_count ?? 0}`, "笔 · available"],
          ["已取消", `${kpi?.canceled_count ?? 0}`, "笔 · 退款回滚"],
          ["风控冻结", `${kpi?.frozen_count ?? 0}`, "笔 · 48h 延长（G11）"],
        ].map(([l, v, s]) => (
          <div key={l as string} className="card" style={{ padding: 16 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>{l as string}</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6, color: l === "风控冻结" && (kpi?.frozen_count ?? 0) > 0 ? "var(--danger)" : "var(--fg)" }}>{v as string}</div>
            <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 4 }}>{s as string}</div>
          </div>
        ))}
      </div>

      {/* 刷单告警 */}
      {(abuse?.items.length ?? 0) > 0 && (
        <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: 6, padding: "12px 16px", fontSize: 13, marginBottom: 16 }}>
          <b>⚠ 检测到批量邀请滥用（G11 detect_batch_abuse）</b>
          <div style={{ marginTop: 6, color: "var(--muted)" }}>
            {abuse!.items.map((u) => (
              <span key={u.inviter_id} style={{ marginRight: 16 }}>用户 <b style={{ color: "var(--fg)" }}>{u.email}</b> 在 {abuse!.window_hours}h 内绑定 {u.bind_count} 个邀请码（阈值 {abuse!.threshold}）</span>
            ))}
          </div>
        </div>
      )}

      {/* 邀请关系列表 */}
      <div className="card" style={{ overflowX: "auto" }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>邀请关系列表 <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>/admin/v1/invites</span></div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>邀请人</th><th style={th}>邀请码</th><th style={th}>下级</th><th style={th}>触发金额</th><th style={th}>奖励</th><th style={th}>核实状态</th><th style={th}>核实至</th>
            </tr>
          </thead>
          <tbody>
            {relations.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>{r.inviter_email}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{r.code || "-"}</td>
                <td style={td}>#{r.invitee_id}</td>
                <td style={td}>{r.trigger_amount_usdt.toFixed(2)}</td>
                <td style={{ ...td, fontWeight: 700, color: "var(--success)" }}>+{r.reward_usdt.toFixed(2)}</td>
                <td style={td}>
                  <span style={{ color: r.status === "available" || r.status === "paid" ? "var(--success)" : r.status === "frozen" || r.status === "canceled" ? "var(--danger)" : r.status === "verifying" ? "var(--warning)" : "var(--muted)" }}>{r.status_label}</span>
                </td>
                <td style={td}>{r.verifying_ends_at?.slice(0, 16) || "-"}</td>
              </tr>
            ))}
            {relations.length === 0 && <tr><td colSpan={7} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无邀请奖励记录</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };