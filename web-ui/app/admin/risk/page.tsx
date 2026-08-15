"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

/** M5 T5.8 风控面板：紧急制动 + 每日亏损限额 + 刷单检测。 */
export default function AdminRiskPage() {
  const router = useRouter();
  const [emergency, setEmergency] = useState(false);
  const [dailyLimit, setDailyLimit] = useState(-1000);
  const [inviterId, setInviterId] = useState("");
  const [flag, setFlag] = useState<boolean | null>(null);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ emergency_stop: boolean; daily_loss_limit_usdt: number }>("/admin/v1/risk/panel", {}, tokenStore.adminAccess);
      setEmergency(r.emergency_stop);
      setDailyLimit(r.daily_loss_limit_usdt);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function saveEmergency(v: boolean) {
    try {
      await apiFetch("/admin/v1/risk/emergency-stop", { method: "POST", body: JSON.stringify({ enabled: v }) }, tokenStore.adminAccess);
      setEmergency(v);
      setMsg(v ? "紧急制动已开启：OPEN/ADD 全部拒绝" : "紧急制动已关闭");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function saveLimit() {
    try {
      await apiFetch("/admin/v1/risk/daily-loss-limit", { method: "POST", body: JSON.stringify({ limit_usdt: Math.abs(dailyLimit) }) }, tokenStore.adminAccess);
      setMsg("每日亏损限额已更新");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function checkAbuse() {
    try {
      const r = await apiFetch<{ flagged: boolean }>("/admin/v1/risk/abuse-check", { method: "POST", body: JSON.stringify({ inviter_id: Number(inviterId) }) }, tokenStore.adminAccess);
      setFlag(r.flagged);
      setMsg(r.flagged ? "⚠ 检测到批量刷单行为" : "未检测到刷单");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "检测失败");
    }
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>风控面板</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

      <div className="card" style={{ marginBottom: 16, padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <div style={{ fontWeight: 700 }}>全局紧急制动</div>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>开启后所有 OPEN/ADD 跟单拒绝，仅放行平仓（CLOSE/REDUCE）</div>
          </div>
          <button className="btn" style={{ border: emergency ? "1px solid var(--danger)" : "1px solid var(--rule)", color: emergency ? "var(--danger)" : "var(--muted)", background: emergency ? "rgba(239,68,68,.12)" : "transparent", padding: "8px 18px" }} onClick={() => saveEmergency(!emergency)}>
            {emergency ? "已开启 - 点击关闭" : "未开启 - 点击开启"}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16, padding: 24 }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>每日亏损限额</div>
        <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 14 }}>当日已实现亏损低于该值后，拒绝新增 OPEN/ADD</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input className="input" style={{ width: 200 }} type="number" value={Math.abs(dailyLimit)} onChange={(e) => setDailyLimit(-Math.abs(Number(e.target.value) || 0))} />
          <span style={{ color: "var(--muted)", fontSize: 13 }}>USDT</span>
          <button className="btn btn-primary" onClick={saveLimit}>保存</button>
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>邀请刷单检测（★T4.9）</div>
        <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 14 }}>1h 内 ≥3 个下级只买试用套餐 → 判定刷单，奖励核实期延长至 48h</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input className="input" style={{ width: 200 }} placeholder="邀请人 user_id" value={inviterId} onChange={(e) => setInviterId(e.target.value)} />
          <button className="btn btn-primary" onClick={checkAbuse} disabled={!inviterId}>检测</button>
          {flag !== null && <span style={{ color: flag ? "var(--danger)" : "var(--success)", fontSize: 13 }}>{flag ? "疑似刷单" : "正常"}</span>}
        </div>
      </div>
    </div>
  );
}
