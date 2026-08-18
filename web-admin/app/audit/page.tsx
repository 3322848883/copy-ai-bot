"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Audit = {
  id: number; actor_id: number; action: string; target_type: string; target_id: string;
  before: string | null; after: string | null; reason: string | null; ip: string | null; created_at: string;
};

const ACT_LABEL: Record<string, string> = {
  "payment.manual_confirmed": "强制确认支付", "payment.manual_failed": "支付标记失败",
  "payment.address.create": "新增收款地址", "payment.address.update": "修改收款地址", "payment.address.delete": "删除收款地址",
  "withdrawal.approve": "通过提现", "withdrawal.reject": "驳回提现", "withdrawal.fill_tx": "填写 TxHash", "withdrawal.retry": "重试发放", "withdrawal.refund": "退还申请",
  "strategy.listed": "上架信号源", "strategy.force_list": "强制上架信号源", "strategy.paused": "暂停策略", "strategy.delisted": "下架策略",
  "strategy.gray": "调整灰度", "strategy.risk_update": "更新策略风控", "strategy.sync_profile": "同步画像",
  "user.freeze": "冻结/解冻用户", "user.note_update": "更新用户备注",
  "wallet.adjust": "手动调整余额", "apikey.bind": "绑定 API", "apikey.unbind": "解绑 API",
  "auth.change_password": "修改密码",
  "identity.bind_invite": "绑定邀请码", "identity.bind_exchange_invite": "绑定交易所邀请码", "identity.auto_mark_sub_account": "标记子账户",
  "risk.rule_update": "更新风控参数", "risk.emergency_stop": "紧急制动", "risk.daily_loss_limit": "调整当日亏损线", "risk.abuse_check": "刷单检测",
  "settings.rule_update": "更新系统规则", "settings.rules_batch_update": "批量更新规则", "settings.plan_upsert": "保存套餐", "settings.plan_delete": "删除套餐", "settings.template_update": "更新邮件模板",
  "exchange_invite.create": "新增邀请码", "exchange_invite.status": "启停邀请码", "exchange_invite.delete": "删除邀请码",
  "review.approve": "通过主号审核", "review.reject": "驳回主号审核",
  "announcement.create": "新增公告", "announcement.update": "更新公告", "announcement.status": "启停公告", "announcement.delete": "删除公告",
  "signal_source.import": "导入信号源",
};

const ACTION_DOMAINS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部动作" },
  { value: "payment.", label: "支付" },
  { value: "withdrawal.", label: "提现" },
  { value: "user.", label: "用户" },
  { value: "wallet.", label: "余额" },
  { value: "strategy.", label: "策略" },
  { value: "risk.", label: "风控" },
  { value: "settings.", label: "设置" },
  { value: "announcement.", label: "公告" },
  { value: "exchange_invite.", label: "交易所邀请" },
  { value: "review.", label: "主号审核" },
  { value: "identity.", label: "身份" },
  { value: "apikey.", label: "API 密钥" },
];

const DANGER_RE = /manual_confirmed|manual_failed|emergency_stop|user\.freeze|wallet\.adjust|force_list|withdrawal\.(approve|reject|refund)|address\.delete|announcement\.delete|plan_delete|exchange_invite\.delete|rule_update/;

function classify(action: string): { tag: string; label: string } {
  if (DANGER_RE.test(action)) return { tag: "danger", label: "高危" };
  if (/\.create$|\.listed$|plan_upsert|signal_source\.import/.test(action)) return { tag: "create", label: "创建" };
  return { tag: "update", label: "更新" };
}

/** M5 T5.7 审计日志（筛选栏 + 类型标签 + 操作内容高亮 + 分页）。
 *  ★ P1 修复：筛选全部走服务端（actor_id/action/danger）——此前客户端过滤只作用于当前页，
 *  其他页的高危记录被漏掉且 total 与表格矛盾；动作标签对齐后端点分命名。 */
export default function AdminAuditPage() {
  const router = useRouter();
  const [items, setItems] = useState<Audit[]>([]);
  const [total, setTotal] = useState(0);
  const [actorInput, setActorInput] = useState("");
  const [actor, setActor] = useState("");
  const [domain, setDomain] = useState("");
  const [dangerOnly, setDangerOnly] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  // actor 输入防抖 400ms，避免每次按键触发请求
  useEffect(() => {
    const t = setTimeout(() => setActor(actorInput.trim()), 400);
    return () => clearTimeout(t);
  }, [actorInput]);

  const load = useCallback(async (p = 1) => {
    try {
      const qs = new URLSearchParams({ size: String(PAGE_SIZE), page: String(p) });
      if (domain) qs.set("action", domain);
      if (dangerOnly) qs.set("danger", "true");
      const actorNum = Number(actor);
      if (actor && Number.isInteger(actorNum) && actorNum > 0) qs.set("actor_id", String(actorNum));
      const r = await apiFetch<{ items: Audit[]; total: number }>(`/admin/v1/audit?${qs.toString()}`, {}, tokenStore.adminAccess);
      setItems(r.items);
      setTotal(r.total);
      setPage(p);
    } catch { /* ignore */ }
  }, [actor, domain, dangerOnly]);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load(1);
  }, [load, router]);

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
        <span style={{ fontSize: 12, color: "var(--muted)" }}>操作者 ID</span>
        <input className="input" style={{ width: 140, height: 32 }} placeholder="如 1（防抖 400ms）" value={actorInput} onChange={(e) => setActorInput(e.target.value)} />
        <span style={{ fontSize: 12, color: "var(--muted)" }}>操作类型</span>
        <select className="select" style={{ width: 150, height: 32 }} value={domain} onChange={(e) => setDomain(e.target.value)}>
          {ACTION_DOMAINS.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
        <button
          className="btn"
          style={{
            padding: "5px 14px", borderRadius: 999, height: 32, minWidth: 0, fontSize: 12,
            border: dangerOnly ? "1px solid var(--admin-red-border)" : "1px solid var(--rule)",
            background: dangerOnly ? "rgba(239,68,68,0.1)" : "transparent",
            color: dangerOnly ? "var(--admin-red)" : "var(--muted)",
          }}
          onClick={() => setDangerOnly((v) => !v)}
        >
          仅看高危
        </button>
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
              {items.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无审计记录</td></tr>}
              {items.map((e) => {
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
