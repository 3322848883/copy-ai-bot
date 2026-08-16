"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type AuditItem = { id: number; actor_id: number; action: string; created_at: string };
type UserItem = { id: number; email: string; role: string; is_active: boolean; is_frozen: boolean; created_at: string | null };
type PaymentItem = { id: number; amount_usdt: number; status: string; created_at: string | null };
type WdItem = { id: number; amount_usdt: number; status: string; created_at: string | null };

const ACT_LABEL: Record<string, string> = {
  payment_manual_confirm: "强制确认支付", payment_manual_fail: "支付标记失败",
  withdrawal_approve: "通过提现", withdrawal_reject: "驳回提现", withdrawal_fill_tx: "填写 TxHash",
  strategy_list: "信号源上架", strategy_force_list: "强制上架信号源", strategy_pause: "暂停策略", strategy_delist: "下架策略",
  user_freeze: "冻结用户", user_unfreeze: "解冻用户",
  reward_manual_grant: "手动补发奖励", risk_rule_update: "更新风控参数", risk_emergency: "紧急制动",
};

/** M5 T5.9 数据概览（对齐演示稿 admin-dashboard：6 KPI + 告警条 + 最近注册 + 审计流 + 今日待办）。 */
export default function AdminDashboardPage() {
  const router = useRouter();
  const toast = useToast();
  const [users, setUsers] = useState<{ total: number; today: number; recent: UserItem[] }>({ total: 0, today: 0, recent: [] });
  const [pay, setPay] = useState<{ total: number; todayAmount: number; todayCount: number; timeout: number }>({ total: 0, todayAmount: 0, todayCount: 0, timeout: 0 });
  const [wd, setWd] = useState<{ pending: number; amount: number }>({ pending: 0, amount: 0 });
  const [orders, setOrders] = useState(0);
  const [riskCount, setRiskCount] = useState(0);
  const [invite, setInvite] = useState<{ today_amount_usdt: number; today_count: number }>({ today_amount_usdt: 0, today_count: 0 });
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [signalsPending, setSignalsPending] = useState(0);
  const [dateStr, setDateStr] = useState("");

  const load = useCallback(async () => {
    const tk = tokenStore.adminAccess;
    if (!tk) return;
    const d = new Date();
    setDateStr(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
    const todayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    try {
      const [u, p, w, o, r, i, a, s] = await Promise.all([
        apiFetch<{ total: number; items: UserItem[] }>("/admin/v1/users?size=100", {}, tk),
        apiFetch<{ total: number; items: PaymentItem[] }>("/admin/v1/payments?size=100", {}, tk),
        apiFetch<{ items: WdItem[] }>("/admin/v1/withdrawals?status=pending", {}, tk),
        apiFetch<{ total: number }>("/admin/v1/orders?size=1", {}, tk).catch(() => ({ total: 0 })),
        apiFetch<{ items: unknown[] }>("/admin/v1/risk/high-risk", {}, tk).catch(() => ({ items: [] })),
        apiFetch<{ today_amount_usdt: number; today_count: number }>("/admin/v1/invites/kpi", {}, tk).catch(() => ({ today_amount_usdt: 0, today_count: 0 })),
        apiFetch<{ items: AuditItem[] }>("/admin/v1/audit?size=7", {}, tk).catch(() => ({ items: [] })),
        apiFetch<{ items: unknown[] }>("/admin/v1/signals/pending", {}, tk).catch(() => ({ items: [] })),
      ]);
      const todayUsers = u.items.filter((x) => x.created_at && new Date(x.created_at).getTime() >= todayStart).length;
      setUsers({ total: u.total, today: todayUsers, recent: u.items.slice(0, 5) });
      const confirmedToday = p.items.filter((x) => x.status === "confirmed" && x.created_at && new Date(x.created_at).getTime() >= todayStart);
      const timeoutPay = p.items.filter((x) => x.status === "timeout" || x.status === "manual").length;
      setPay({
        total: p.total,
        todayAmount: confirmedToday.reduce((acc, x) => acc + (x.amount_usdt || 0), 0),
        todayCount: confirmedToday.length,
        timeout: timeoutPay,
      });
      setWd({ pending: w.items.length, amount: w.items.reduce((acc, x) => acc + (x.amount_usdt || 0), 0) });
      setOrders(o.total);
      setRiskCount(r.items.length);
      setInvite(i);
      setAudit(a.items);
      setSignalsPending(s.items.length);
    } catch { /* 数据失败不阻塞 */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function exportReport() {
    const rows: string[][] = [
      ["运营报表", dateStr, ""],
      [""],
      ["指标", "数值", "说明"],
      ["注册用户", String(users.total), `今日新增 ${users.today}`],
      ["今日支付额", `${pay.todayAmount.toFixed(2)} USDT`, `${pay.todayCount} 笔`],
      ["跟单订单", String(orders), "全部"],
      ["待审核提现", `${wd.pending} 笔`, `${wd.amount.toFixed(2)} USDT`],
      ["风控告警", String(riskCount), "高危用户"],
      ["今日邀请奖励", `${invite.today_amount_usdt.toFixed(2)} USDT`, `${invite.today_count} 笔`],
      [""],
      ["最近注册用户", "", ""],
      ["ID", "邮箱", "加入时间"],
      ...users.recent.map((u) => [String(u.id), u.email, u.created_at ? new Date(u.created_at).toLocaleString("zh-CN") : ""]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `运营报表_${dateStr}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("success", "运营报表已导出（CSV）");
  }

  const kpis = [
    { l: "注册用户", v: users.total.toLocaleString(), sub: <><span className="u">+{users.today}</span> 今日新增</>, href: "/users" },
    { l: "今日支付额", v: pay.todayAmount.toFixed(1), sub: <>USDT · <span className="u">{pay.todayCount} 笔</span></>, href: "/payments" },
    { l: "跟单订单", v: orders.toLocaleString(), sub: <>CopyOrder 全部</>, href: "/orders" },
    { l: "待审核提现", v: String(wd.pending), sub: <>笔 · 共 {wd.amount.toFixed(1)} USDT</>, href: "/withdrawals" },
    { l: "风控告警", v: String(riskCount), danger: true, sub: <>高危 · 48h 冻结核实</>, href: "/risk" },
    { l: "今日邀请奖励", v: invite.today_amount_usdt.toFixed(1), sub: <>USDT · {invite.today_count} 笔触发</>, href: "/invites" },
  ];

  const todoCount = wd.pending + pay.timeout + signalsPending + riskCount;

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">ADMIN DASHBOARD</div>
          <h1 className="page-title">数据概览<small>{dateStr || "—"} · 实时</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={exportReport}>导出报表</button>
          <button className="btn btn-primary" onClick={() => { load(); toast("success", "数据已刷新"); }}>刷新数据</button>
        </div>
      </div>

      {/* 告警条 */}
      {(riskCount > 0 || wd.pending > 0 || pay.timeout > 0) && (
        <div className="alert-strip">
          <span>⚠</span>
          <span>
            检测到 <strong>{riskCount}</strong> 个高危用户（批量邀请滥用）· <strong>{wd.pending}</strong> 笔提现待审核 · <strong>{pay.timeout}</strong> 笔支付确认超时待人工处理
          </span>
        </div>
      )}

      {/* KPI */}
      <div className="kpi-grid">
        {kpis.map((k) => (
          <Link key={k.l} href={k.href} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="kpi-card">
              <div className="kpi-l">{k.l}</div>
              <div className="kpi-v" style={k.danger && riskCount > 0 ? { color: "#f87171" } : undefined}>{k.v}</div>
              <div className="kpi-s">{k.sub}</div>
            </div>
          </Link>
        ))}
      </div>

      {/* 双栏：最近注册 + 审计流 */}
      <div className="two-col">
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>最近注册用户</div>
            <span className="panel-sub">/admin/v1/users</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="ftx-table">
              <thead><tr><th>用户</th><th>角色</th><th className="num">ID</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                {users.recent.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>暂无用户</td></tr>}
                {users.recent.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{u.email}</td>
                    <td>{u.role === "user" ? "普通用户" : u.role}</td>
                    <td className="num">{u.id}</td>
                    <td>{u.is_frozen ? <span className="badge badge-err">冻结</span> : <span className="badge badge-ok">正常</span>}</td>
                    <td><Link href={`/users?id=${u.id}`} style={{ color: "var(--accent)", cursor: "pointer" }}>详情</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>审计日志流</div>
            <span className="panel-sub">/admin/v1/audit · 实时</span>
          </div>
          <div className="audit-list">
            {audit.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>暂无审计事件</div>}
            {audit.map((e) => {
              const t = e.created_at ? new Date(e.created_at) : null;
              const time = t ? `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}` : "—";
              return (
                <div key={e.id} className="audit-item">
                  <span className="a-time">{time}</span>
                  <span className="a-op">admin{e.actor_id}</span>
                  <span className="a-txt">{ACT_LABEL[e.action] || e.action}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 今日待办 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>今日待办</div>
          <span className="panel-sub">{todoCount} 项待处理</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead><tr><th>类型</th><th>目标</th><th>详情</th><th>优先级</th><th>操作</th></tr></thead>
            <tbody>
              {todoCount === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>全部处理完毕 🎉</td></tr>}
              {wd.pending > 0 && (
                <tr>
                  <td>提现审核</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>待审核</td>
                  <td className="sub-ref">{wd.pending} 笔 · 共 {wd.amount.toFixed(1)} USDT 待处理</td>
                  <td><span className="badge badge-err">高</span></td>
                  <td><Link href="/withdrawals" style={{ color: "var(--accent)" }}>审核</Link></td>
                </tr>
              )}
              {pay.timeout > 0 && (
                <tr>
                  <td>支付确认</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>超时/人工</td>
                  <td className="sub-ref">{pay.timeout} 笔轮询超时 · 待人工处理</td>
                  <td><span className="badge badge-warn">中</span></td>
                  <td><Link href="/payments" style={{ color: "var(--accent)" }}>处理</Link></td>
                </tr>
              )}
              {signalsPending > 0 && (
                <tr>
                  <td>信号源</td>
                  <td>待选池</td>
                  <td className="sub-ref">{signalsPending} 个候选带单员待 G04 审核</td>
                  <td><span className="badge badge-warn">中</span></td>
                  <td><Link href="/strategies" style={{ color: "var(--accent)" }}>审核</Link></td>
                </tr>
              )}
              {riskCount > 0 && (
                <tr>
                  <td>风控</td>
                  <td>高危用户</td>
                  <td className="sub-ref">批量邀请滥用 · 建议冻结 48h</td>
                  <td><span className="badge badge-err">高</span></td>
                  <td><Link href="/risk" style={{ color: "var(--accent)" }}>处理</Link></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
