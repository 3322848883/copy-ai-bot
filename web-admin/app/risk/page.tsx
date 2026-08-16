"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Rules = Record<string, number | boolean>;
type HighRiskUser = { user_id: number; email: string; trigger: string; bind_1h: number; frozen_amount_usdt: number; status: string };
type Strategy = {
  id: number;
  display_name: string;
  max_drawdown: number;
  status: string;
  risk?: { max_order_notional: number; max_drawdown_pct: number; max_order_notional_set?: boolean; max_drawdown_pct_set?: boolean };
};

/** 风控中心：全局参数 4 卡 + 策略级风控 + 高危用户 + 紧急制动/限额/刷单检测。 */
export default function AdminRiskPage() {
  const router = useRouter();
  const toast = useToast();
  const [emergency, setEmergency] = useState(false);
  const [dailyLimit, setDailyLimit] = useState(-1000);
  const [rules, setRules] = useState<Rules>({});
  const [highRisk, setHighRisk] = useState<HighRiskUser[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [inviterId, setInviterId] = useState("");
  const [flag, setFlag] = useState<boolean | null>(null);
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [stratEdit, setStratEdit] = useState<Strategy | null>(null);
  const [stratOrder, setStratOrder] = useState("");
  const [stratDraw, setStratDraw] = useState("");

  const load = useCallback(async () => {
    try {
      const [p, r, h, s] = await Promise.all([
        apiFetch<{ emergency_stop: boolean; daily_loss_limit_usdt: number }>("/admin/v1/risk/panel", {}, tokenStore.adminAccess),
        apiFetch<{ rules: Rules }>("/admin/v1/risk/rules", {}, tokenStore.adminAccess).catch(() => ({ rules: {} })),
        apiFetch<{ items: HighRiskUser[] }>("/admin/v1/risk/high-risk", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
        apiFetch<{ items: Strategy[] }>("/admin/v1/signals", {}, tokenStore.adminAccess).catch(() => ({ items: [] })),
      ]);
      setEmergency(p.emergency_stop);
      setDailyLimit(p.daily_loss_limit_usdt);
      setRules(r.rules);
      setHighRisk(h.items);
      setStrategies(s.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function saveEmergency(v: boolean) {
    try {
      await apiFetch("/admin/v1/risk/emergency-stop", { method: "POST", body: JSON.stringify({ enabled: v }) }, tokenStore.adminAccess);
      setEmergency(v);
      toast(v ? "warn" : "success", v ? "紧急制动已开启：OPEN/ADD 全部拒绝" : "紧急制动已关闭");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function saveLimit() {
    try {
      await apiFetch("/admin/v1/risk/daily-loss-limit", { method: "POST", body: JSON.stringify({ limit_usdt: Math.abs(dailyLimit) }) }, tokenStore.adminAccess);
      toast("success", "每日亏损限额已更新");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function checkAbuse() {
    try {
      const r = await apiFetch<{ flagged: boolean }>("/admin/v1/risk/abuse-check", { method: "POST", body: JSON.stringify({ inviter_id: Number(inviterId) }) }, tokenStore.adminAccess);
      setFlag(r.flagged);
      toast(r.flagged ? "warn" : "success", r.flagged ? "⚠ 检测到批量刷单行为" : "未检测到刷单");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "检测失败");
    }
  }

  async function reviewHighRisk(u: HighRiskUser, freeze: boolean) {
    try {
      await apiFetch(
        `/admin/v1/users/${u.user_id}/freeze`,
        { method: "PATCH", body: JSON.stringify({ frozen: freeze }) },
        tokenStore.adminAccess,
      );
      setHighRisk((prev) => prev.filter((x) => x.user_id !== u.user_id));
      toast("success", freeze ? `已冻结 ${u.email}（复核中）` : `已解除风控标记 ${u.email}`);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function saveRule(key: string, value: number | boolean) {
    try {
      await apiFetch("/admin/v1/risk/rules", { method: "POST", body: JSON.stringify({ key, value }) }, tokenStore.adminAccess);
      setRules((prev) => ({ ...prev, [key]: value }));
      toast("success", "风控参数已更新（audit 留痕）");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "更新失败");
    }
  }

  function openStratEdit(s: Strategy) {
    setStratEdit(s);
    setStratOrder(String(s.risk?.max_order_notional ?? 2000));
    setStratDraw(String(s.risk?.max_drawdown_pct ?? 25));
  }

  async function saveStratRisk() {
    if (!stratEdit) return;
    const order = Number(stratOrder);
    const draw = Number(stratDraw);
    if (Number.isNaN(order) || Number.isNaN(draw) || order <= 0 || draw <= 0) {
      toast("error", "请输入大于 0 的数值");
      return;
    }
    try {
      await apiFetch(
        `/admin/v1/signals/${stratEdit.id}/risk`,
        { method: "PATCH", body: JSON.stringify({ max_order_notional: order, max_drawdown_pct: draw }) },
        tokenStore.adminAccess,
      );
      setStrategies((prev) => prev.map((s) => (s.id === stratEdit.id ? { ...s, risk: { max_order_notional: order, max_drawdown_pct: draw, max_order_notional_set: true, max_drawdown_pct_set: true } } : s)));
      toast("success", "策略风控已更新（audit 留痕）");
      setStratEdit(null);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "更新失败");
    }
  }

  function openEdit(key: string, val: number | boolean) {
    setEditKey(key);
    setEditVal(String(val));
  }

  function confirmEdit() {
    if (!editKey) return;
    const meta = RULE_META[editKey];
    if (meta?.bool) return;
    const n = Number(editVal);
    if (Number.isNaN(n)) {
      toast("error", "请输入数字");
      return;
    }
    saveRule(editKey, n);
    setEditKey(null);
  }

  const fmt = (v: number | boolean | undefined, unit: string) => {
    if (v === undefined) return "—";
    if (typeof v === "boolean") return v ? "开启" : "关闭";
    return `${typeof v === "number" ? v.toLocaleString() : v}${unit}`;
  };

  return (
    <div>
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">RISK CENTER · 风控中心</div>
          <h1 className="page-title">风控中心<small>全局 / 策略级参数 · 高危用户 · 滥用检测</small></h1>
        </div>
      </div>

      {/* 全局告警 */}
      {highRisk.length > 0 && (
        <div className="risk-alert">
          <span style={{ fontSize: 16, color: "#f87171" }}>⚠</span>
          <div>
            <div className="ra-title">{highRisk.length} 个高危用户待处理（批量邀请滥用）</div>
            <div className="ra-desc">已自动冻结奖励（48h 核实）· 建议人工复核账号关联</div>
          </div>
        </div>
      )}

      {/* 全局风控参数 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>全局风控参数</div>
          <span className="panel-sub">/admin/v1/risk/rules</span>
        </div>
        <div className="params-grid">
          <div className="param-card">
            <div className="param-name">跟单延迟红线</div>
            <div className="param-desc">信号处理超过阈值即丢弃（模式 A / 模式 B）</div>
            <div className="param-row"><span className="param-label">模式 A</span><span className="param-val">{fmt(rules.delay_red_line_a, "s")}</span><button className="edit-btn" onClick={() => openEdit("delay_red_line_a", rules.delay_red_line_a ?? 10)}>编辑</button></div>
            <div className="param-row"><span className="param-label">模式 B（V2）</span><span className="param-val">{fmt(rules.delay_red_line_b, "s")}</span><button className="edit-btn" onClick={() => openEdit("delay_red_line_b", rules.delay_red_line_b ?? 5)}>编辑</button></div>
          </div>
          <div className="param-card">
            <div className="param-name">单机器人名义上限</div>
            <div className="param-desc">单 bot 名义价值上限（USDT）</div>
            <div className="param-row"><span className="param-label">默认上限</span><span className="param-val">{fmt(rules.notional_limit, "")}</span><button className="edit-btn" onClick={() => openEdit("notional_limit", rules.notional_limit ?? 10000)}>编辑</button></div>
            <div className="param-row">
              <span className="param-label">白名单豁免</span>
              <span className="param-val">{fmt(rules.whitelist_exempt, "")}</span>
              <span className={`toggle${rules.whitelist_exempt === false ? " off" : ""}`} onClick={() => saveRule("whitelist_exempt", rules.whitelist_exempt === false)}></span>
            </div>
          </div>
          <div className="param-card">
            <div className="param-name">提现风控</div>
            <div className="param-desc">G13 门槛 + G11 邀请风控</div>
            <div className="param-row"><span className="param-label">最低提现</span><span className="param-val">{fmt(rules.min_withdrawal, " USDT")}</span><button className="edit-btn" onClick={() => openEdit("min_withdrawal", rules.min_withdrawal ?? 10)}>编辑</button></div>
            <div className="param-row"><span className="param-label">手续费</span><span className="param-val">{fmt(rules.withdrawal_fee, " USDT")}</span><button className="edit-btn" onClick={() => openEdit("withdrawal_fee", rules.withdrawal_fee ?? 1)}>编辑</button></div>
            <div className="param-row"><span className="param-label">批量邀请核实</span><span className="param-val">{fmt(rules.batch_invite_verify_hours, "h")}</span><button className="edit-btn" onClick={() => openEdit("batch_invite_verify_hours", rules.batch_invite_verify_hours ?? 48)}>编辑</button></div>
          </div>
          <div className="param-card">
            <div className="param-name">跨所拦截</div>
            <div className="param-desc">机器人策略所 ≠ 所选所时拦截开启</div>
            <div className="param-row">
              <span className="param-label">跨所拦截</span>
              <span className="param-val">{fmt(rules.cross_exchange_block, "")}</span>
              <span className={`toggle${rules.cross_exchange_block === false ? " off" : ""}`} onClick={() => saveRule("cross_exchange_block", rules.cross_exchange_block === false)}></span>
            </div>
            <div className="param-row"><span className="param-label">API 提现权限</span><span className="param-val" style={{ color: "#f87171" }}>强制拒绝</span></div>
          </div>
        </div>
      </div>

      {/* 紧急制动 + 每日亏损限额 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>紧急制动与限额</div>
          <span className="panel-sub">/admin/v1/risk/emergency-stop · daily-loss-limit</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <div style={{ fontWeight: 700 }}>全局紧急制动</div>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>开启后所有 OPEN/ADD 跟单拒绝，仅放行平仓（CLOSE/REDUCE）</div>
          </div>
          <button className="btn" style={{ border: emergency ? "1px solid var(--danger)" : "1px solid var(--rule)", color: emergency ? "var(--danger)" : "var(--muted)", background: emergency ? "rgba(239,68,68,.12)" : "transparent", padding: "8px 18px" }} onClick={() => saveEmergency(!emergency)}>
            {emergency ? "已开启 - 点击关闭" : "未开启 - 点击开启"}
          </button>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>每日亏损限额</span>
          <input className="input" style={{ width: 200 }} type="number" value={Math.abs(dailyLimit)} onChange={(e) => setDailyLimit(-Math.abs(Number(e.target.value) || 0))} />
          <span style={{ color: "var(--muted)", fontSize: 13 }}>USDT</span>
          <button className="btn btn-primary" onClick={saveLimit}>保存</button>
        </div>
      </div>

      {/* 策略级风控 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>策略级风控</div>
          <span className="panel-sub">/admin/v1/risk/strategies/:id</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>策略</th><th className="num">最大回撤上限</th><th className="num">单笔上限</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {strategies.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>暂无线上策略</td></tr>
              )}
              {strategies.map((s) => (
                <tr key={s.id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{s.display_name}</td>
                  <td className="num" style={{ color: s.risk?.max_drawdown_pct && s.max_drawdown > s.risk.max_drawdown_pct ? "#f87171" : undefined }}>
                    {s.risk?.max_drawdown_pct != null ? `${s.risk.max_drawdown_pct.toFixed(1)}%` : "25.0%"}
                    {s.risk?.max_drawdown_pct_set ? "" : "（默认）"}
                  </td>
                  <td className="num">{s.risk?.max_order_notional != null ? s.risk.max_order_notional.toLocaleString() : "2,000"}</td>
                  <td>{s.status === "listed" ? <span className="badge badge-ok">正常</span> : <span className="badge badge-warn">关注</span>}</td>
                  <td><button className="edit-btn" onClick={() => openStratEdit(s)}>编辑</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 高危用户列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>高危用户列表</div>
          <span className="panel-sub">批量滥用检测 · detect_batch_abuse（1h 窗口）</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>用户</th><th>触发规则</th><th className="num">1h 绑定数</th><th className="num">冻结奖励</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {highRisk.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--muted)" }}>暂无高危用户</td></tr>
              )}
              {highRisk.map((u) => (
                <tr key={u.user_id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{u.email}</td>
                  <td>{u.trigger}</td>
                  <td className="num">{u.bind_1h}</td>
                  <td className="num">{u.frozen_amount_usdt.toFixed(2)}</td>
                  <td><span className="badge badge-err">{u.status}</span></td>
                  <td>
                    <button className="action-link" onClick={() => reviewHighRisk(u, true)}>复核</button>
                    {" · "}
                    <button className="action-link danger" onClick={() => reviewHighRisk(u, false)}>解除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 邀请刷单检测 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>邀请刷单检测（★T4.9）</div>
          <span className="panel-sub">/admin/v1/risk/abuse-check</span>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input className="input" style={{ width: 200 }} placeholder="邀请人 user_id" value={inviterId} onChange={(e) => setInviterId(e.target.value)} />
          <button className="btn btn-primary" onClick={checkAbuse} disabled={!inviterId}>检测</button>
          {flag !== null && <span style={{ color: flag ? "var(--danger)" : "var(--success)", fontSize: 13 }}>{flag ? "疑似刷单" : "正常"}</span>}
        </div>
      </div>

      {/* 参数编辑弹窗 */}
      {editKey && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">编辑「{RULE_META[editKey]?.label || editKey}」</div>
              <button className="modal-close" onClick={() => setEditKey(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">数值{RULE_META[editKey]?.unit ? `（${RULE_META[editKey].unit}）` : ""}</label>
              <input className="input" type="number" value={editVal} onChange={(e) => setEditVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && confirmEdit()} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditKey(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={confirmEdit}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 策略级风控编辑弹窗 */}
      {stratEdit && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">策略风控「{stratEdit.display_name}」</div>
              <button className="modal-close" onClick={() => setStratEdit(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">单笔上限（USDT）</label>
              <input className="input" type="number" value={stratOrder} onChange={(e) => setStratOrder(e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">最大回撤上限（%）</label>
              <input className="input" type="number" value={stratDraw} onChange={(e) => setStratDraw(e.target.value)} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setStratEdit(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveStratRisk}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const RULE_META: Record<string, { label: string; unit: string; bool?: boolean }> = {
  delay_red_line_a: { label: "跟单延迟红线·模式A", unit: "s" },
  delay_red_line_b: { label: "跟单延迟红线·模式B", unit: "s" },
  notional_limit: { label: "单机器人名义上限", unit: "USDT" },
  min_withdrawal: { label: "最低提现", unit: "USDT" },
  withdrawal_fee: { label: "手续费", unit: "USDT" },
  batch_invite_verify_hours: { label: "批量邀请核实", unit: "h" },
};
