"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Plan = { plan_id: string; name: string; price_usdt: number; duration_days: number; trial: boolean };
type Order = { order_id: number; amount_usdt: number; network: string; status: string; required_confirmations: number; confirmations?: number };
type SubStatus = { active: boolean; plan_id?: string; expires_at?: string };

const NETWORKS = [
  { key: "trc20", label: "TRC-20", note: "12 确认" },
  { key: "bep20", label: "BEP-20", note: "15 确认" },
  { key: "erc20", label: "ERC-20", note: "12 确认" },
];

/** M4 T4.10 套餐购买：选套餐 → 选网络 → 提交 TxHash → 状态轮询。 */
export default function SubscriptionsPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [sub, setSub] = useState<SubStatus | null>(null);
  const [plan, setPlan] = useState("");
  const [network, setNetwork] = useState("trc20");
  const [order, setOrder] = useState<Order | null>(null);
  const [txHash, setTxHash] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

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
        setTxHash("");
        load();
      } else if (o.status === "failed") {
        setErr("支付校验失败（地址/金额/状态），订单已拒绝");
        setOrder(null);
      } else {
        setMsg(`确认中（${o.confirmations}/${o.required_confirmations}），系统将自动轮询`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>订阅套餐</div>
          {sub?.active ? (
            <div style={{ color: "var(--success)", fontSize: 13, marginTop: 6 }}>
              订阅有效至 {sub.expires_at?.slice(0, 10)}（{sub.plan_id === "trial_5u" ? "试用" : "正式"}）
            </div>
          ) : (
            <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 6 }}>未订阅，开通后即可跟单</div>
          )}
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {/* 套餐选择 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
          {plans.map((p) => (
            <div
              key={p.plan_id}
              className="card"
              onClick={() => { setPlan(p.plan_id); setOrder(null); }}
              style={{ cursor: "pointer", border: plan === p.plan_id ? "1px solid var(--accent)" : undefined, transition: "border-color .2s" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 700 }}>{p.name}</div>
                {p.trial && <span style={{ fontSize: 11, color: "var(--accent)", background: "var(--accent-soft)", padding: "2px 8px", borderRadius: 12 }}>限购 1 次</span>}
              </div>
              <div style={{ fontSize: 22, fontWeight: 800, margin: "12px 0 4px" }}>{p.price_usdt} <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 400 }}>USDT</span></div>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>{p.duration_days} 天 · 三链支付自动核验</div>
            </div>
          ))}
        </div>

        {/* 下单流程 */}
        {!order ? (
          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 12 }}>选择支付网络</div>
            <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
              {NETWORKS.map((n) => (
                <button
                  key={n.key}
                  className="btn"
                  style={{
                    border: network === n.key ? "1px solid var(--accent)" : "1px solid var(--rule)",
                    color: network === n.key ? "var(--accent)" : "var(--fg)",
                    background: network === n.key ? "var(--accent-soft)" : "var(--surface)",
                  }}
                  onClick={() => setNetwork(n.key)}
                >
                  {n.label} <span style={{ fontSize: 11, opacity: 0.7 }}>{n.note}</span>
                </button>
              ))}
            </div>
            <button className="btn btn-primary" onClick={createOrder} disabled={busy || !plan}>
              {busy ? "创建中…" : "创建支付订单"}
            </button>
          </div>
        ) : (
          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>
              订单 #{order.order_id} · 待支付 {order.amount_usdt} USDT（{NETWORKS.find((n) => n.key === order.network)?.label}）
            </div>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 12 }}>
              请向平台收款地址转账后，粘贴交易哈希（TxHash）完成校验
            </div>
            <input
              className="input"
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="粘贴 TxHash（dev 环境输入 mock_confirm_xxx 或 mock_slow_xxx）"
              value={txHash}
              onChange={(e) => setTxHash(e.target.value)}
            />
            <button className="btn btn-primary" onClick={submitTx} disabled={busy || !txHash}>
              {busy ? "校验中…" : "提交 TxHash"}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
