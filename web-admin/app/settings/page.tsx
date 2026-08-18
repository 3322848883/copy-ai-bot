"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Val = number | boolean | string;
type Rules = Record<string, Val>;
type Plan = { plan_id: string; name: string; price_usdt: number; duration_days: number; trial: boolean; max_purchase: number | null; enabled: boolean };
type Template = { key: string; subject: string; html: string };

type RULE_META = { label: string; unit: string; bool?: boolean; str?: boolean; secret?: boolean };

const RULE_META: Record<string, RULE_META> = {
  verify_code_enabled: { label: "注册邮箱验证码", unit: "", bool: true },
  verify_code_ttl_min: { label: "验证码有效期", unit: "min" },
  verify_code_max_attempts: { label: "最大错误尝试", unit: "次" },
  verify_code_dev_code: { label: "dev 固定验证码", unit: "", str: true },
  verify_code_length: { label: "验证码位数", unit: "位" },
  referral_reward_pct: { label: "邀请奖励比例", unit: "%" },
  referral_verify_hours: { label: "邀请核实期", unit: "h" },
  referral_abuse_trial_threshold: { label: "刷单检测·试用订单阈值", unit: "笔/h" },
  referral_abuse_verify_hours: { label: "风控延长核实期", unit: "h" },
  chain_confirm_trc20: { label: "TRC-20 确认数", unit: "块" },
  chain_confirm_bep20: { label: "BEP-20 确认数", unit: "块" },
  chain_confirm_erc20: { label: "ERC-20 确认数", unit: "块" },
  chain_confirm_aptos: { label: "APTOS 确认数", unit: "块" },
  payment_order_ttl_min: { label: "支付订单倒计时", unit: "min" },
  mail_enabled: { label: "邮件发送", unit: "", bool: true },
  smtp_host: { label: "SMTP 主机", unit: "", str: true },
  smtp_port: { label: "SMTP 端口", unit: "" },
  smtp_user: { label: "SMTP 账号", unit: "", str: true },
  smtp_password: { label: "SMTP 密码", unit: "", str: true, secret: true },
  mail_from: { label: "发件人地址", unit: "", str: true },
  support_email: { label: "客服邮箱", unit: "", str: true },
  support_telegram: { label: "客服 Telegram", unit: "", str: true },
};

const GROUP_ORDER = ["验证码", "邀请奖励", "链上确认", "支付订单", "邮件", "客服联系"];

/** 系统设置：验证码 / 邀请奖励 / 链上确认 + 邮件模板 + 订阅套餐。 */
export default function AdminSettingsPage() {
  const router = useRouter();
  const toast = useToast();
  const [rules, setRules] = useState<Rules>({});
  const [templates, setTemplates] = useState<Record<string, Template>>({});
  const [plans, setPlans] = useState<Plan[]>([]);

  const [editKey, setEditKey] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [editTplKey, setEditTplKey] = useState<string | null>(null);
  const [editTpl, setEditTpl] = useState<Template>({ key: "", subject: "", html: "" });
  const [editPlan, setEditPlan] = useState<Plan | null | "new">(null);
  const [planForm, setPlanForm] = useState<Plan>({ plan_id: "", name: "", price_usdt: 0, duration_days: 30, trial: false, max_purchase: null, enabled: true });

  const load = useCallback(async () => {
    try {
      const [r, t, p] = await Promise.all([
        apiFetch<{ rules: Rules }>("/admin/v1/settings/rules", {}, tokenStore.adminAccess),
        apiFetch<{ templates: Record<string, Template> }>("/admin/v1/settings/templates", {}, tokenStore.adminAccess),
        apiFetch<{ plans: Plan[] }>("/admin/v1/settings/plans", {}, tokenStore.adminAccess),
      ]);
      setRules(r.rules);
      setTemplates(t.templates);
      setPlans(p.plans);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "加载失败");
    }
  }, [toast]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function saveRule(key: string, value: Val) {
    try {
      await apiFetch("/admin/v1/settings/rules", { method: "POST", body: JSON.stringify({ key, value }) }, tokenStore.adminAccess);
      setRules((prev) => ({ ...prev, [key]: value }));
      toast("success", "设置已更新（audit 留痕）");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "更新失败");
    }
  }

  function openEdit(key: string, val: Val) {
    setEditKey(key);
    setEditVal(String(val));
  }

  function confirmEdit() {
    if (!editKey) return;
    const meta = RULE_META[editKey];
    if (meta?.bool) return;
    if (meta?.str) {
      // 文本/机密字段：机密留空或占位则不发（保留原值）
      if (meta.secret && (editVal === "" || editVal === "********")) {
        toast("success", "密码留空，已保留原值");
        setEditKey(null);
        return;
      }
      saveRule(editKey, editVal);
      setEditKey(null);
      return;
    }
    const n = Number(editVal);
    if (Number.isNaN(n)) {
      toast("error", "请输入数字");
      return;
    }
    saveRule(editKey, n);
    setEditKey(null);
  }

  function openTpl(key: string) {
    setEditTplKey(key);
    setEditTpl({ subject: templates[key]?.subject || "", html: templates[key]?.html || "", key });
  }

  async function saveTpl() {
    if (!editTplKey) return;
    try {
      await apiFetch("/admin/v1/settings/templates", { method: "POST", body: JSON.stringify({ key: editTplKey, subject: editTpl.subject, html: editTpl.html }) }, tokenStore.adminAccess);
      setTemplates((prev) => ({ ...prev, [editTplKey]: { ...editTpl, key: editTplKey } }));
      toast("success", "模板已保存");
      setEditTplKey(null);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "保存失败");
    }
  }

  function openPlanNew() {
    setEditPlan("new");
    setPlanForm({ plan_id: "", name: "", price_usdt: 0, duration_days: 30, trial: false, max_purchase: null, enabled: true });
  }

  function openPlanEdit(p: Plan) {
    setEditPlan(p);
    setPlanForm({ ...p });
  }

  async function savePlan() {
    try {
      await apiFetch("/admin/v1/settings/plans", { method: "POST", body: JSON.stringify(planForm) }, tokenStore.adminAccess);
      toast("success", "套餐已保存");
      setEditPlan(null);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "保存失败");
    }
  }

  async function deletePlan(plan_id: string) {
    try {
      await apiFetch(`/admin/v1/settings/plans/${plan_id}`, { method: "DELETE" }, tokenStore.adminAccess);
      toast("success", "套餐已删除");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "删除失败");
    }
  }

  const fmt = (v: Val | undefined, unit: string) => {
    if (v === undefined) return "—";
    if (typeof v === "boolean") return v ? "开启" : "关闭";
    return `${typeof v === "number" ? v.toLocaleString() : v}${unit}`;
  };

  const grouped = GROUP_ORDER.map((g) => ({ group: g, keys: Object.keys(RULE_META).filter((k) => groupOf(k) === g) }));

  return (
    <div>
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">SYSTEM SETTINGS · 系统设置</div>
          <h1 className="page-title">系统设置<small>验证码 · 邀请奖励 · 链上确认 · 邮件模板 · 订阅套餐</small></h1>
        </div>
      </div>

      {/* 平台参数 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>平台参数</div>
          <span className="panel-sub">/admin/v1/settings/rules</span>
        </div>
        <div className="params-grid">
          {grouped.map(({ group, keys }) => (
            <div className="param-card" key={group}>
              <div className="param-name">{GROUP_META[group]?.name ?? group}</div>
              <div className="param-desc">{GROUP_META[group]?.desc ?? ""}</div>
              {keys.map((key) => {
                const meta = RULE_META[key];
                return (
                  <div className="param-row" key={key}>
                    <span className="param-label">{meta.label}</span>
                    <span className="param-val">{fmt(rules[key], meta.unit)}</span>
                    {meta.bool ? (
                      <span className={`toggle${rules[key] === false ? " off" : ""}`} onClick={() => saveRule(key, rules[key] !== false)}></span>
                    ) : (
                      <button className="edit-btn" onClick={() => openEdit(key, rules[key] ?? 0)}>编辑</button>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* 邮件模板 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>邮件模板</div>
          <span className="panel-sub">/admin/v1/settings/templates · 支持 {codeVar} / {nameVar} / {ttlVar}</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>模板</th><th>主题</th><th>操作</th></tr>
            </thead>
            <tbody>
              {Object.entries(templates).map(([key, t]) => (
                <tr key={key}>
                  <td>{key === "verify_code" ? "邮箱验证码模板" : "订阅临期提醒模板"}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{t.subject}</td>
                  <td><button className="edit-btn" onClick={() => openTpl(key)}>编辑</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 订阅套餐 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>订阅套餐</div>
          <span className="panel-sub">/admin/v1/settings/plans · 全站订阅实时生效</span>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button className="btn btn-primary" onClick={openPlanNew}>+ 新增套餐</button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>ID</th><th>名称</th><th className="num">价格</th><th className="num">时长</th><th>类型</th><th>限购</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {plans.length === 0 && <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--muted)" }}>暂无套餐</td></tr>}
              {plans.map((p) => (
                <tr key={p.plan_id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{p.plan_id}</td>
                  <td>{p.name}</td>
                  <td className="num">{p.price_usdt.toFixed(2)} USDT</td>
                  <td className="num">{p.duration_days} 天</td>
                  <td>{p.trial ? <span className="badge badge-warn">试用</span> : <span className="badge badge-ok">正式</span>}</td>
                  <td className="num">{p.max_purchase ?? "不限"}</td>
                  <td>{p.enabled ? <span className="badge badge-ok">启用</span> : <span className="badge badge-muted">停用</span>}</td>
                  <td>
                    <button className="edit-btn" onClick={() => openPlanEdit(p)}>编辑</button>
                    {" · "}
                    <button className="action-link danger" onClick={() => deletePlan(p.plan_id)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
              <label className="field-label">数值{RULE_META[editKey]?.unit ? `（${RULE_META[editKey].unit}）` : ""}{RULE_META[editKey]?.secret ? "（留空保留原值）" : ""}</label>
              {RULE_META[editKey]?.str ? (
                <input
                  className="input"
                  type={RULE_META[editKey]?.secret ? "password" : "text"}
                  value={editVal}
                  onChange={(e) => setEditVal(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && confirmEdit()}
                  placeholder={RULE_META[editKey]?.secret ? "留空保留原密码" : ""}
                  autoComplete="off"
                />
              ) : (
                <input className="input" type="number" value={editVal} onChange={(e) => setEditVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && confirmEdit()} />
              )}
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditKey(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={confirmEdit}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 模板编辑弹窗 */}
      {editTplKey && (
        <div className="modal-overlay">
          <div className="modal" style={{ width: 640, maxWidth: "92vw" }}>
            <div className="modal-hdr">
              <div className="modal-title">编辑邮件模板</div>
              <button className="modal-close" onClick={() => setEditTplKey(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">邮件主题</label>
              <input className="input" value={editTpl.subject} onChange={(e) => setEditTpl({ ...editTpl, subject: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">HTML 模板（{codeVar} 验证码 · {ttlVar} 有效期 · {nameVar} 昵称 · {expiresVar} 到期时间）</label>
              <textarea className="input" style={{ minHeight: 180, fontFamily: "var(--font-geist-mono), monospace", fontSize: 12 }} value={editTpl.html} onChange={(e) => setEditTpl({ ...editTpl, html: e.target.value })} />
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditTplKey(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveTpl}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 套餐编辑弹窗 */}
      {editPlan !== null && (
        <div className="modal-overlay">
          <div className="modal" style={{ width: 560, maxWidth: "92vw" }}>
            <div className="modal-hdr">
              <div className="modal-title">{editPlan === "new" ? "新增套餐" : `编辑「${editPlan.plan_id}」`}</div>
              <button className="modal-close" onClick={() => setEditPlan(null)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">套餐 ID（字母数字下划线，创建后不可改）</label>
              <input className="input" disabled={editPlan !== "new"} value={planForm.plan_id} onChange={(e) => setPlanForm({ ...planForm, plan_id: e.target.value })} />
            </div>
            <div className="field">
              <label className="field-label">名称</label>
              <input className="input" value={planForm.name} onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })} />
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">价格（USDT）</label>
                <input className="input" type="number" step="0.1" value={planForm.price_usdt} onChange={(e) => setPlanForm({ ...planForm, price_usdt: Number(e.target.value) || 0 })} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">时长（天）</label>
                <input className="input" type="number" value={planForm.duration_days} onChange={(e) => setPlanForm({ ...planForm, duration_days: Number(e.target.value) || 0 })} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">限购次数（空=不限）</label>
                <input className="input" type="number" value={planForm.max_purchase ?? ""} onChange={(e) => setPlanForm({ ...planForm, max_purchase: e.target.value === "" ? null : Number(e.target.value) })} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">类型</label>
                <select className="input" value={planForm.trial ? "trial" : "normal"} onChange={(e) => setPlanForm({ ...planForm, trial: e.target.value === "trial" })}>
                  <option value="normal">正式</option>
                  <option value="trial">试用</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label className="field-label">启用</label>
              <span className={`toggle${planForm.enabled ? "" : " off"}`} onClick={() => setPlanForm({ ...planForm, enabled: !planForm.enabled })}></span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setEditPlan(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={savePlan}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function groupOf(key: string): string {
  if (key.startsWith("verify_code")) return "验证码";
  if (key.startsWith("referral")) return "邀请奖励";
  if (key.startsWith("payment_order")) return "支付订单";
  if (key.startsWith("mail") || key.startsWith("smtp")) return "邮件";
  if (key.startsWith("support")) return "客服联系";
  return "链上确认";
}

const GROUP_META: Record<string, { name: string; desc: string }> = {
  验证码: { name: "注册邮箱验证码", desc: "注册/登录邮箱验证码开关与参数" },
  邀请奖励: { name: "邀请奖励", desc: "返佣比例与核实期" },
  链上确认: { name: "链上确认数", desc: "支付按网络所需确认数" },
  支付订单: { name: "支付订单", desc: "支付订单待支付倒计时" },
  邮件: { name: "邮件", desc: "邮件总开关 + SMTP 服务器参数（凭密码留空保存保留原值）" },
  客服联系: { name: "客服联系", desc: "前台页脚/忘记密码/支付教程展示的客服渠道，留空则前台不展示" },
};

const codeVar = "{code}";
const ttlVar = "{ttl}";
const nameVar = "{name}";
const expiresVar = "{expires}";