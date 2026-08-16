"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Plan = { plan_id: string; name: string; price_usdt: number; duration_days: number; trial: boolean };
type Order = {
  order_id: number;
  amount_usdt: number;
  network: string;
  status: string;
  required_confirmations?: number;
  required?: number;
  confirmations?: number;
  plan_id?: string;
  platform_address?: string;
  note?: string;
};
type SubStatus = { active: boolean; plan_id?: string; expires_at?: string };
type Toast = { type: "success" | "warn" | "info" | "error"; msg: string };

const NETWORKS = [
  { key: "trc20", label: "TRC-20", note: "12 确认" },
  { key: "bep20", label: "BEP-20", note: "15 确认" },
  { key: "erc20", label: "ERC-20", note: "12 确认" },
];
const PENDING_LIMIT_MS = 30 * 60 * 1000; // 30min 订单倒计时

/** M4 T4.10 订阅：推荐标签 + 套餐卡（正式上试用下）+ 订单信息卡 + 订阅状态卡 + 支付状态机。 */
export default function SubscriptionsPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [sub, setSub] = useState<SubStatus | null>(null);
  const [plan, setPlan] = useState("");
  const [network, setNetwork] = useState("trc20");
  const [order, setOrder] = useState<Order | null>(null);
  const [orderCreatedAt, setOrderCreatedAt] = useState<number | null>(null);
  const [txHash, setTxHash] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [nowTick, setNowTick] = useState(Date.now());
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((type: Toast["type"], m: string) => {
    setToasts((t) => [...t, { type, msg: m }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.msg !== m || x.type !== type)), 3400);
  }, []);

  const load = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        apiFetch<{ plans: Plan[] }>("/v1/subscriptions/plans"),
        apiFetch<SubStatus>("/v1/subscriptions/me", {}, tokenStore.access),
      ]);
      setPlans(p.plans);
      setSub(s);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    load();
    const timer = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [load, router]);

  async function createOrder() {
    setBusy(true);
    setErr("");
    try {
      const o = await apiFetch<Order>("/v1/payments", {
        method: "POST",
        body: JSON.stringify({ plan_id: plan, network }),
      }, tokenStore.access);
      setOrder(o);
      setOrderCreatedAt(Date.now());
      setTxHash("");
      setMsg(`订单已创建，请向平台地址转入 ${o.amount_usdt} USDT`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "创建订单失败");
    } finally {
      setBusy(false);
    }
  }

  async function submitTx() {
    if (!order) return;
    setBusy(true);
    setErr("");
    try {
      const o = await apiFetch<Order>(`/v1/payments/${order.order_id}/tx`, {
        method: "POST",
        body: JSON.stringify({ tx_hash: txHash }),
      }, tokenStore.access);
      setOrder(o);
      if (o.status === "confirmed") {
        setMsg("支付已确认，订阅已激活！");
        setOrder(null);
        setOrderCreatedAt(null);
        setTxHash("");
        load();
      } else if (o.status === "failed") {
        setErr("支付校验失败（地址/金额/状态），订单已拒绝");
        setOrder(null);
        setOrderCreatedAt(null);
      } else {
        setMsg(`确认中（${o.confirmations ?? 0}/${o.required ?? o.required_confirmations ?? 0}），系统将自动轮询`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  // ★ verifying 轮询：GET /v1/payments/{id}（1/5/10/20 分钟轮询的前端进度展示）
  useEffect(() => {
    if (!order || (order.status !== "verifying" && order.status !== "polling")) return;
    const timer = setInterval(async () => {
      try {
        const o = await apiFetch<Order>(`/v1/payments/${order.order_id}`, {}, tokenStore.access);
        setOrder(o);
        if (o.status === "confirmed") {
          setMsg("支付已确认，订阅已激活！");
          setOrder(null);
          setOrderCreatedAt(null);
          setTxHash("");
          load();
        } else if (o.status === "failed") {
          setErr("支付校验失败（地址/金额/状态），订单已拒绝");
          setOrder(null);
          setOrderCreatedAt(null);
        }
      } catch {
        /* 轮询失败忽略 */
      }
    }, 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order?.order_id, order?.status]);

  /* ── 订阅状态卡 ── */
  const sortedPlans = [...plans].sort((a, b) => Number(a.trial) - Number(b.trial)); // 正式上试用下
  const planName = (pid?: string) => {
    const p = plans.find((x) => x.plan_id === pid);
    return p ? p.name : pid === "trial_5u" ? "试用版" : pid ? "正式版" : "—";
  };
  const subDuration = sub?.active && sub.plan_id ? plans.find((p) => p.plan_id === sub.plan_id)?.duration_days ?? 30 : 30;
  const subLeftMs = sub?.active && sub.expires_at ? Math.max(0, new Date(sub.expires_at).getTime() - nowTick) : 0;
  const subLeftDays = Math.ceil(subLeftMs / 86400_000);
  const subProgress = sub?.active ? Math.min(100, Math.max(0, ((1 - subLeftMs / (subDuration * 86400_000)) * 100))) : 0;

  /* ── 支付状态机 ── */
  const pendingLeft = orderCreatedAt && order?.status === "pending" ? Math.max(0, PENDING_LIMIT_MS - (nowTick - orderCreatedAt)) : 0;
  const required = order?.required ?? order?.required_confirmations ?? 0;
  const confirmPct = order && required > 0 ? Math.min(100, Math.round(((order.confirmations ?? 0) / required) * 100)) : 0;

  async function copyAddress() {
    if (!order?.platform_address) return;
    try {
      await navigator.clipboard.writeText(order.platform_address);
      showToast("success", "收款地址已复制");
    } catch {
      showToast("warn", "复制失败，请手动复制");
    }
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="page-wrap">
        {/* 页头 */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">SUBSCRIBE &amp; PAY · 订阅支付</div>
            <h1 className="page-title">订阅套餐<small>三链支付 · 自动核验 · 立即开通跟单</small></h1>
          </div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {/* 订阅状态卡 / G10 过期黄条 */}
        {sub?.active ? (
          <div
            className="panel"
            style={{ marginBottom: 24, border: "1px solid var(--accent)", background: "rgba(0,212,170,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, flexWrap: "wrap" }}
          >
            <div style={{ flex: 1, minWidth: 260 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
                <span className="badge badge-ok">订阅中</span>
                <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 12, color: "var(--muted)" }}>
                  有效期至 {sub.expires_at?.slice(0, 10)}
                </span>
              </div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{planName(sub.plan_id)}</div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>剩余 {subLeftDays} 天</div>
              <div style={{ height: 4, background: "var(--surface)", borderRadius: 999, marginTop: 12, overflow: "hidden" }}>
                <div style={{ width: `${subProgress}%`, height: "100%", background: "var(--accent)", borderRadius: 999 }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button className="btn btn-primary" style={{ height: 44, padding: "0 28px" }} onClick={() => { setOrder(null); setOrderCreatedAt(null); setErr(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                续费
              </button>
              <button className="btn btn-secondary" style={{ height: 44, padding: "0 28px" }} onClick={() => showToast("info", "历史支付记录可在个人中心 · 订阅状态中查看")}>
                查看记录
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* G10 过期黄条 */}
            <div style={{ marginBottom: 16, padding: 12, borderRadius: 6, border: "1px solid rgba(234,179,8,0.3)", background: "rgba(234,179,8,0.06)", fontSize: 12, color: "var(--warning)", lineHeight: 1.6 }}>
              ⚠ 订阅已过期 / 未开通（G10）：CopyBot 自动暂停开仓（OPEN/ADD 拦截），平仓（REDUCE/CLOSE）放行；续费后立即恢复跟单。
            </div>
            <div className="empty-state" style={{ minHeight: 160, marginBottom: 24 }}>
              <div className="es-ic">◇</div>
              <div style={{ fontSize: 13 }}>未开通订阅，选择下方套餐即可开始跟单</div>
            </div>
          </>
        )}

        {/* 套餐选择（正式上试用下，试用置灰） */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 16, marginBottom: 24 }}>
          {sortedPlans.map((p) => {
            const selected = plan === p.plan_id;
            const formal = !p.trial;
            return (
              <div
                key={p.plan_id}
                onClick={() => { setPlan(p.plan_id); setOrder(null); setOrderCreatedAt(null); setErr(""); }}
                style={{
                  position: "relative", border: selected ? "1px solid var(--accent)" : "1px solid var(--rule)",
                  borderRadius: 10, padding: 16, cursor: "pointer", transition: "border-color .2s",
                  opacity: p.trial ? 0.75 : 1, background: selected ? "rgba(0,212,170,0.05)" : "var(--surface)",
                }}
              >
                {formal && (
                  <span style={{ position: "absolute", top: -9, right: 12, padding: "2px 10px", borderRadius: 4, fontSize: 10, fontFamily: "var(--font-geist-mono), monospace", border: "1px solid var(--accent)", color: "var(--accent)", background: "rgba(0,212,170,0.06)" }}>
                    推荐
                  </span>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{p.name}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
                      {p.trial ? "体验 7 天 · 最多 1 个机器人" : "全部策略 + 无限跟单机器人"}
                    </div>
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-geist-mono), monospace" }}>
                    {p.price_usdt.toFixed(1)}<span style={{ fontSize: 12, color: "var(--muted)" }}>U</span>
                  </div>
                </div>
                {p.trial && <span className="tag" style={{ marginTop: 8 }}>限购 1 次</span>}
                <button
                  className={formal ? "btn btn-primary" : "btn btn-secondary"}
                  style={{ marginTop: 12, width: "100%", height: 44 }}
                  onClick={(e) => { e.stopPropagation(); setPlan(p.plan_id); setOrder(null); setOrderCreatedAt(null); setErr(""); }}
                >
                  {selected ? "已选择" : `选择${p.name}`}
                </button>
              </div>
            );
          })}
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", textAlign: "center", marginBottom: 24 }}>
          绑定平台邀请码的用户享免订阅权益
        </div>

        {/* 下单流程 */}
        {!order ? (
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>选择支付网络</div>
              <span className="panel-sub">TRC-20 / BEP-20 / ERC-20 三链自动核验</span>
            </div>
            <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
              {NETWORKS.map((n) => (
                <button
                  key={n.key}
                  className="btn"
                  style={{
                    flex: 1, border: network === n.key ? "1px solid var(--accent)" : "1px solid var(--rule)",
                    color: network === n.key ? "var(--accent)" : "var(--fg)",
                    background: network === n.key ? "var(--accent-soft)" : "var(--surface)",
                  }}
                  onClick={() => setNetwork(n.key)}
                >
                  {n.label} <span style={{ fontSize: 11, opacity: 0.7 }}>{n.note}</span>
                </button>
              ))}
            </div>
            <button className="btn btn-primary" style={{ height: 44, padding: "0 32px" }} onClick={createOrder} disabled={busy || !plan}>
              {busy ? "创建中…" : "创建支付订单"}
            </button>
          </div>
        ) : (
          /* 支付订单信息卡 */
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>订单信息</div>
              <span className="panel-sub">#{order.order_id} · 请 30 分钟内完成转账</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>订单号</span>
                <span style={{ fontFamily: "var(--font-geist-mono), monospace" }}>#{order.order_id}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>套餐</span>
                <span>{planName(order.plan_id || plan)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>金额</span>
                <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{order.amount_usdt.toFixed(2)} USDT</span>
              </div>
              <div style={{ height: 1, background: "var(--rule)", margin: "4px 0" }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <span style={{ color: "var(--muted)", flexShrink: 0 }}>收款地址</span>
                <span style={{ fontFamily: "var(--font-geist-mono), monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>
                  {order.platform_address ? `${order.platform_address.slice(0, 6)}…${order.platform_address.slice(-4)}` : "未配置"}
                </span>
                {order.platform_address && (
                  <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 11, height: 28, flexShrink: 0 }} onClick={copyAddress}>复制地址</button>
                )}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--muted)" }}>网络</span>
                <span style={{ display: "flex", gap: 6 }}>
                  {NETWORKS.map((n) => (
                    <span key={n.key} className="tag" style={n.key === order.network ? { borderColor: "var(--accent)", color: "var(--accent)", background: "rgba(0,212,170,0.06)" } : undefined}>
                      {n.label}
                    </span>
                  ))}
                </span>
              </div>
            </div>

            {/* QR 占位 */}
            <div style={{ border: "1px dashed var(--rule)", borderRadius: 6, padding: 12, display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
              <div style={{ width: 52, height: 52, background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 4, display: "grid", placeItems: "center", fontSize: 9, color: "var(--muted)" }}>
                QR
              </div>
              <div style={{ fontSize: 10, color: "var(--muted)", lineHeight: 1.7 }}>
                扫码转账（或复制地址）
                <br />转账完成后提交 TxHash
              </div>
            </div>

            {/* TxHash 提交 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
              <label className="label">交易哈希 TxHash</label>
              <input
                className="input"
                style={{ fontFamily: "var(--font-geist-mono), monospace" }}
                placeholder="0x 或 9f 开头的交易哈希（dev 可输入 mock_confirm_xxx）"
                value={txHash}
                onChange={(e) => setTxHash(e.target.value)}
              />
              {order.status === "verifying" && (
                <div style={{ fontSize: 12, color: "var(--success)" }}>✓ 即时校验通过，等待链上确认（1/5/10/20 分钟轮询）</div>
              )}
            </div>
            <button className="btn btn-primary" style={{ width: "100%", height: 48, fontSize: 16, marginTop: 12 }} onClick={submitTx} disabled={busy || !txHash}>
              {busy ? "校验中…" : "提交并验证"}
            </button>

            {/* 支付状态机 UI */}
            {order.status === "pending" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid var(--rule)", background: "rgba(59,130,246,0.05)", fontSize: 12, color: "#60a5fa", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <span>订单待支付 · 超时自动关闭</span>
                <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>
                  倒计时 {String(Math.floor(pendingLeft / 60000)).padStart(2, "0")}:{String(Math.floor((pendingLeft % 60000) / 1000)).padStart(2, "0")}
                </span>
              </div>
            )}
            {order.status === "verifying" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid rgba(59,130,246,0.35)", background: "rgba(59,130,246,0.06)", fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", color: "#60a5fa", marginBottom: 8 }}>
                  <span>链上确认中 · 系统自动轮询</span>
                  <span style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{order.confirmations ?? 0}/{required}</span>
                </div>
                <div style={{ height: 6, background: "#070e1a", borderRadius: 999, overflow: "hidden" }}>
                  <div style={{ width: `${confirmPct}%`, height: "100%", background: "linear-gradient(90deg, #3b82f6, #60a5fa)", borderRadius: 999, transition: "width .6s ease" }} />
                </div>
              </div>
            )}
            {order.status === "confirmed" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid rgba(40,196,100,0.4)", background: "rgba(40,196,100,0.06)", fontSize: 12, color: "var(--success)" }}>
                ✓ 支付已确认，订阅已激活 · 邮件通知已发送
              </div>
            )}
            {order.status === "failed" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid rgba(239,68,68,0.4)", background: "rgba(239,68,68,0.06)", fontSize: 12, color: "var(--danger)" }}>
                支付校验失败（网络不符 / 金额不足 / Tx 失败）· 可重新提交
              </div>
            )}
            {order.status === "timeout" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid rgba(234,179,8,0.3)", background: "rgba(234,179,8,0.06)", fontSize: 12, color: "var(--warning)" }}>
                ⚠ 确认超时，已提交人工处理（后台管理员将核实到账）
              </div>
            )}
            {order.status === "manual" && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, border: "1px solid rgba(234,179,8,0.3)", background: "rgba(234,179,8,0.06)", fontSize: 12, color: "var(--warning)" }}>
                ⚠ 需要人工介入 · 请联系客服处理（后台管理员强制确认）
              </div>
            )}
            {order.note && (
              <div style={{ marginTop: 8, fontSize: 11, color: "var(--tertiary)" }}>{order.note}</div>
            )}
          </div>
        )}
      </div>

      {/* Toast 栈 */}
      <div className="toast-stack">
        {toasts.map((t, i) => (
          <div key={i} className={`toast ${t.type}`}>
            <span className="t-ic">{t.type === "success" ? "✓" : t.type === "warn" ? "!" : t.type === "error" ? "✕" : "i"}</span>
            <span>{t.msg}</span>
            <button className="t-close" onClick={() => setToasts((x) => x.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
      </div>
    </main>
  );
}
