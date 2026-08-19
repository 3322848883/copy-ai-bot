"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Kpi = { today_count: number; today_amount_usdt: number; verifying_count: number; available_count: number; canceled_count: number; frozen_count: number };
type Abuse = { items: { inviter_id: number; email: string; bind_count: number }[]; threshold: number; window_hours: number };
type Relation = { id: number; inviter_email: string; code: string; invitee_id: number; trigger_amount_usdt: number; reward_usdt: number; status: string; status_label: string; verifying_ends_at: string | null; created_at: string | null };

const MONO = "var(--font-geist-mono), monospace";

/** M5 邀请奖励：10% 返佣看板（KPI 卡）+ 刷单告警（G11）+ 邀请关系列表。 */
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

  /** 核实状态 → 徽章（对齐设计稿：核实中/冻结/已到账/已取消）。 */
  function statusBadge(status: string, label: string) {
    switch (status) {
      case "verifying":
        return <span className="badge badge-info">{label}</span>;
      case "frozen":
      case "paid_failed":
        return <span className="badge badge-err">{label}</span>;
      case "available":
      case "paid":
        return <span className="badge badge-ok">{label}</span>;
      case "canceled":
      case "rolled_back":
        return <span className="badge badge-warn">{label}</span>;
      default:
        return <span className="badge badge-muted">{label}</span>;
    }
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">REFERRAL REWARDS · 邀请奖励</div>
          <h1 className="page-title">邀请奖励<small>10% 奖励 · 24h/48h 核实 · 风控看板</small></h1>
        </div>
      </div>

      {/* KPI 卡（对齐设计稿：今日触发/核实中/已到账/已取消/风控冻结） */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-l">今日触发奖励</div>
          <div className="kpi-v">{kpi?.today_count ?? 0}</div>
          <div className="kpi-s">笔 · {kpi?.today_amount_usdt?.toFixed(2) ?? "0.00"} USDT</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">核实中</div>
          <div className="kpi-v" style={{ color: "#60a5fa" }}>{kpi?.verifying_count ?? 0}</div>
          <div className="kpi-s">笔 · 24h/48h</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">已到账</div>
          <div className="kpi-v" style={{ color: "var(--success)" }}>{kpi?.available_count ?? 0}</div>
          <div className="kpi-s">笔 · available</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">已取消</div>
          <div className="kpi-v">{kpi?.canceled_count ?? 0}</div>
          <div className="kpi-s">笔 · 下级退款回滚</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-l">风控冻结</div>
          <div className="kpi-v" style={{ color: "var(--danger)" }}>{kpi?.frozen_count ?? 0}</div>
          <div className="kpi-s">笔 · 48h 延长</div>
        </div>
      </div>

      {/* 刷单告警（G11 detect_batch_abuse） */}
      {(abuse?.items.length ?? 0) > 0 && abuse && (
        <div className="risk-alert">
          <span style={{ fontSize: 16, color: "#f87171" }}>⚠</span>
          <div>
            <div className="ra-title">检测到批量邀请滥用</div>
            <div className="ra-desc">
              {abuse.items.map((u) => (
                <span key={u.inviter_id} style={{ marginRight: 16 }}>
                  用户 <strong style={{ color: "var(--fg)" }}>{u.email}</strong> 在 {abuse.window_hours}h 内绑定 {u.bind_count} 个邀请码（阈值 {abuse.threshold}），已标记高危并将相关奖励冻结 48h 核实。
                </span>
              ))}
              <span style={{ display: "block", marginTop: 4 }}>
                <button className="action-link" onClick={() => router.push("/risk")}>前往风控中心处理 →</button>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 邀请关系列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>邀请关系列表</div>
          <span className="panel-sub">/admin/v1/invites</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>邀请人</th><th>邀请码</th><th>下级</th><th className="num">触发金额</th><th className="num">奖励</th><th>核实状态</th><th>核实至</th></tr>
            </thead>
            <tbody>
              {relations.map((r) => {
                const canceled = r.status === "canceled" || r.status === "rolled_back";
                const frozen = r.status === "frozen" || r.status === "paid_failed";
                const ends = r.verifying_ends_at?.slice(0, 16) || r.created_at?.slice(0, 16) || "-";
                return (
                  <tr key={r.id}>
                    <td style={{ fontFamily: MONO }}>{r.inviter_email}</td>
                    <td style={{ fontFamily: MONO }}>{r.code || "-"}</td>
                    <td style={{ fontFamily: MONO }}>#{r.invitee_id}</td>
                    <td className="num">{r.trigger_amount_usdt.toFixed(2)}</td>
                    <td className="num" style={{ color: canceled ? "#f87171" : "var(--success)" }}>+{r.reward_usdt.toFixed(2)}</td>
                    <td>{statusBadge(r.status, r.status_label)}</td>
                    <td className="sub-ref">
                      {canceled ? "24h 内下级退款" : frozen ? `${ends}（48h 风控）` : r.status === "verifying" ? `${ends}（24h）` : ends}
                    </td>
                  </tr>
                );
              })}
              {relations.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无邀请奖励记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
