"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Balance = { available_usdt: number };
type WdResult = { id: number; amount_usdt: number; fee_usdt: number; status: string };
type WdItem = {
  id: number;
  amount_usdt: number;
  fee_usdt: number;
  network: string;
  address: string;
  status: string;
  tx_hash: string | null;
  reject_reason: string | null;
  created_at: string | null;
};

const NETWORKS = [
  { key: "trc20", label: "TRC-20", placeholder: "T 开头 34 位地址", regex: /^T[1-9A-HJ-NP-Za-km-z]{33}$/ },
  { key: "bep20", label: "BEP-20", placeholder: "0x 开头 42 位地址", regex: /^0x[a-fA-F0-9]{40}$/ },
  { key: "erc20", label: "ERC-20", placeholder: "0x 开头 42 位地址", regex: /^0x[a-fA-F0-9]{40}$/ },
];
const NET_LABEL: Record<string, string> = { trc20: "TRC-20", bep20: "BEP-20", erc20: "ERC-20" };
const WD_STATUS: Record<string, { label: string; color: string }> = {
  pending_review: { label: "审核中", color: "var(--warning)" },
  approved: { label: "已通过待打款", color: "var(--accent)" },
  processing: { label: "打款中", color: "var(--accent)" },
  paid: { label: "已打款", color: "var(--success)" },
  rejected: { label: "已驳回", color: "var(--danger)" },
  canceled: { label: "已取消", color: "var(--muted)" },
  expired: { label: "已过期", color: "var(--muted)" },
};

/** M4 T4.12 提现表单：网络 + 地址正则 + 最低门槛提示 + 实时到账计算。 */
export default function WithdrawPage() {
  const router = useRouter();
  const [available, setAvailable] = useState(0);
  const [network, setNetwork] = useState("trc20");
  const [address, setAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // ★ 提现记录列表 + 详情
  const [records, setRecords] = useState<WdItem[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, w] = await Promise.all([
        apiFetch<Balance>("/v1/rewards/balance", {}, tokenStore.access),
        apiFetch<{ items: WdItem[] }>("/v1/withdrawals", {}, tokenStore.access),
      ]);
      setAvailable(b.available_usdt);
      setRecords(w.items);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  const net = NETWORKS.find((n) => n.key === network)!;
  const amt = parseFloat(amount) || 0;
  const addrOk = net.regex.test(address.trim());
  const amountOk = amt >= 10 && amt <= available;

  async function submit() {
    if (!addrOk || !amountOk) return;
    setBusy(true);
    setErr("");
    try {
      const wd = await apiFetch<WdResult>("/v1/withdrawals", {
        method: "POST",
        body: JSON.stringify({ network, address: address.trim(), amount_usdt: amt }),
      }, tokenStore.access);
      setMsg(`提现申请已提交（#${wd.id}），实发 ${(wd.amount_usdt - wd.fee_usdt).toFixed(2)} USDT，等待审核`);
      setAddress("");
      setAmount("");
      load();
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
      <div style={{ maxWidth: 620, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>提现申请</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>可提现 {available.toFixed(2)} USDT · 最低 10U · 手续费 1U</div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        <div className="card">
          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            {NETWORKS.map((n) => (
              <button
                key={n.key}
                className="btn"
                style={{
                  flex: 1,
                  border: network === n.key ? "1px solid var(--accent)" : "1px solid var(--rule)",
                  color: network === n.key ? "var(--accent)" : "var(--fg)",
                  background: network === n.key ? "var(--accent-soft)" : "var(--surface)",
                }}
                onClick={() => { setNetwork(n.key); setErr(""); }}
              >
                {n.label}
              </button>
            ))}
          </div>

          <label className="label">收款地址（{net.label}）</label>
          <input
            className="input"
            style={{ width: "100%", marginBottom: 4 }}
            placeholder={net.placeholder}
            value={address}
            onChange={(e) => { setAddress(e.target.value); setErr(""); }}
          />
          {address && !addrOk && <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 8 }}>地址格式不正确（{net.label}）</div>}

          <label className="label" style={{ marginTop: 12 }}>提现金额（USDT）</label>
          <input
            className="input"
            style={{ width: "100%", marginBottom: 4 }}
            type="number"
            placeholder="≥ 10"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          {amount && !amountOk && (
            <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 8 }}>
              {amt < 10 ? "低于最低提现门槛 10U" : "超过可提现余额"}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "12px 0", borderTop: "1px solid var(--rule)", marginTop: 12 }}>
            <span style={{ color: "var(--muted)" }}>手续费</span>
            <span>1.00 USDT</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, paddingBottom: 12 }}>
            <span style={{ color: "var(--muted)" }}>预计到账</span>
            <span style={{ fontWeight: 700 }}>{(amt - 1).toFixed(2)} USDT</span>
          </div>

          <button className="btn btn-primary" style={{ width: "100%" }} disabled={busy || !addrOk || !amountOk} onClick={submit}>
            {busy ? "提交中…" : "提交提现申请"}
          </button>
        </div>

        {/* ★ 提现记录列表 + 详情（GET /v1/withdrawals） */}
        <div style={{ fontWeight: 600, marginTop: 28, marginBottom: 12 }}>提现记录（近 50 笔）</div>
        {records.length === 0 ? (
          <div className="card" style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", padding: 28 }}>
            暂无提现记录
          </div>
        ) : (
          records.map((wd) => {
            const st = WD_STATUS[wd.status] || { label: wd.status, color: "var(--muted)" };
            const open = expandedId === wd.id;
            return (
              <div key={wd.id} className="card" style={{ marginBottom: 10, padding: 14 }}>
                <div
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                  onClick={() => setExpandedId(open ? null : wd.id)}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>#{wd.id} · {NET_LABEL[wd.network] || wd.network}</div>
                    <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 2 }}>
                      {wd.created_at ? new Date(wd.created_at).toLocaleString("zh-CN") : "—"} · {wd.amount_usdt.toFixed(2)} USDT
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 12, padding: "3px 10px", borderRadius: 20, background: st.color + "22", color: st.color }}>
                      {st.label}
                    </span>
                    <span style={{ color: "var(--muted)", fontSize: 12 }}>{open ? "收起" : "详情"}</span>
                  </div>
                </div>
                {open && (
                  <div style={{ borderTop: "1px solid var(--rule)", marginTop: 12, paddingTop: 12, fontSize: 13 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "6px 12px" }}>
                      <span style={{ color: "var(--muted)" }}>收款地址</span><span style={{ wordBreak: "break-all" }}>{wd.address}</span>
                      <span style={{ color: "var(--muted)" }}>申请金额</span><span>{wd.amount_usdt.toFixed(2)} USDT</span>
                      <span style={{ color: "var(--muted)" }}>手续费</span><span>{wd.fee_usdt.toFixed(2)} USDT</span>
                      <span style={{ color: "var(--muted)" }}>实发金额</span><span>{(wd.amount_usdt - wd.fee_usdt).toFixed(2)} USDT</span>
                      <span style={{ color: "var(--muted)" }}>网络</span><span>{NET_LABEL[wd.network] || wd.network}</span>
                      <span style={{ color: "var(--muted)" }}>状态</span><span style={{ color: st.color }}>{st.label}</span>
                      {wd.tx_hash && (
                        <>
                          <span style={{ color: "var(--muted)" }}>交易哈希</span><span style={{ wordBreak: "break-all", color: "var(--accent)" }}>{wd.tx_hash}</span>
                        </>
                      )}
                      {wd.reject_reason && (
                        <>
                          <span style={{ color: "var(--muted)" }}>驳回原因</span><span style={{ color: "var(--danger)" }}>{wd.reject_reason}</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </main>
  );
}
