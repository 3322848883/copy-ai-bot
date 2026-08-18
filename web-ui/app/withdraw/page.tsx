"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Balance = { available_usdt: number; withdraw_params?: { min_withdrawal_usdt: number; fee_usdt: number } };
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
  { key: "trc20", label: "TRC-20", note: "Tron · 到账快", placeholder: "TX…（TRC-20）", regex: /^T[1-9A-HJ-NP-Za-km-z]{33}$/ },
  { key: "bep20", label: "BEP-20", note: "BNB Chain", placeholder: "0x…（BEP-20）", regex: /^0x[a-fA-F0-9]{40}$/ },
  { key: "erc20", label: "ERC-20", note: "Ethereum · 需 Gas", placeholder: "0x…（ERC-20）", regex: /^0x[a-fA-F0-9]{40}$/ },
  { key: "aptos", label: "APTOS", note: "Aptos · 快", placeholder: "0x…（APTOS）", regex: /^0x[a-fA-F0-9]{1,64}$/ },
];
const NET_LABEL: Record<string, string> = { trc20: "TRC-20", bep20: "BEP-20", erc20: "ERC-20", aptos: "APTOS" };
const WD_STATUS: Record<string, { label: string; cls: string }> = {
  pending_review: { label: "审核中", cls: "badge-info" },
  approved: { label: "已通过待打款", cls: "badge-info" },
  processing: { label: "打款中", cls: "badge-info" },
  paid: { label: "已打款", cls: "badge-ok" },
  rejected: { label: "审核驳回", cls: "badge-warn" },
  canceled: { label: "已取消", cls: "badge-err" },
  expired: { label: "已过期", cls: "badge-muted" },
};
const WD_MSG: Record<string, string> = {
  pending_review: "等待管理员审核",
  approved: "审核通过 · 待链上打款",
  processing: "打款中 · 等待链上确认",
  paid: "已打款 · 链上确认",
  rejected: "审核驳回 · 资金已退回可提现余额",
  canceled: "管理员退还申请 · 资金已回退",
  expired: "超时未审核自动取消",
};

/** M4 T4.12 提现：余额卡 + 二次确认弹窗 + 双栏布局 + 地址 ✓ 校验 + 记录状态详情卡。 */
export default function WithdrawPage() {
  const router = useRouter();
  const [available, setAvailable] = useState(0);
  const [feeUsdt, setFeeUsdt] = useState(1);
  const [minUsdt, setMinUsdt] = useState(10);
  const [network, setNetwork] = useState("trc20");
  const [address, setAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // ★ 提现记录 + 展开详情
  const [records, setRecords] = useState<WdItem[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // ★ 二次确认弹窗
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [b, w] = await Promise.all([
        apiFetch<Balance>("/v1/rewards/balance", {}, tokenStore.access),
        apiFetch<{ items: WdItem[] }>("/v1/withdrawals", {}, tokenStore.access),
      ]);
      setAvailable(b.available_usdt);
      if (b.withdraw_params) {
        setFeeUsdt(Number(b.withdraw_params.fee_usdt) || 0);
        setMinUsdt(Number(b.withdraw_params.min_withdrawal_usdt) || 10);
      }
      setRecords(w.items);
      setExpandedId((cur) => cur ?? (w.items[0]?.id ?? null));
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
  const amountOk = amt >= minUsdt && amt <= available;
  const addrMasked = address.trim() ? `${address.trim().slice(0, 4)}…${address.trim().slice(-4)}` : "—";

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

  function openConfirm() {
    if (!addrOk || !amountOk) return;
    setConfirmOpen(true);
  }
  function confirmSubmit() {
    setConfirmOpen(false);
    void submit();
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="page-wrap">
        {/* 页头 */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">WITHDRAWAL · 提现</div>
            <h1 className="page-title">提现<small>奖励余额 · 人工审核 · 链上打款</small></h1>
          </div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {/* 双栏布局 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(440px, 1fr))", gap: 24, alignItems: "start" }}>
          {/* 左：提现表单 */}
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>申请提现</div>
              <span className="panel-sub">最低 {minUsdt} U · 手续费 {feeUsdt} U</span>
            </div>

            {/* 余额卡（30px 数字 + 全部提取） */}
            <div
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between", padding: 16,
                borderRadius: 10, border: "1px solid rgba(0,212,170,0.35)",
                background: "linear-gradient(135deg, rgba(0,212,170,0.07), var(--surface))",
              }}
            >
              <div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>可提现余额</div>
                <div style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 30, fontWeight: 700, fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
                  {available.toFixed(2)} <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400 }}>USDT</span>
                </div>
              </div>
              <button className="btn btn-secondary" style={{ height: 28, padding: "0 12px", fontSize: 12 }} onClick={() => { setAmount(String(available)); setErr(""); }}>
                全部提取
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 16 }}>
              <label className="label" style={{ display: "flex", justifyContent: "space-between" }}>
                提现金额 <span style={{ color: "var(--tertiary)", fontWeight: 400 }}>最低 {minUsdt} USDT</span>
              </label>
              <input
                className="input"
                style={{ height: 48, fontFamily: "var(--font-geist-mono), monospace" }}
                type="number"
                placeholder="10.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              {amount && !amountOk && (
                <div style={{ fontSize: 12, color: "var(--danger)" }}>
                  {amt < minUsdt ? `最低提现 ${minUsdt} USDT，且不超过可提现余额` : "超过可提现余额"}
                </div>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12 }}>
              <label className="label">网络</label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12 }}>
                {NETWORKS.map((n) => (
                  <div
                    key={n.key}
                    onClick={() => { setNetwork(n.key); setAddress(""); setErr(""); }}
                    style={{
                      border: network === n.key ? "1px solid var(--accent)" : "1px solid var(--rule)",
                      borderRadius: 6, padding: 12, cursor: "pointer", display: "flex", flexDirection: "column", gap: 2,
                      transition: "all .2s", background: network === n.key ? "rgba(0,212,170,0.08)" : "#070e1a",
                      boxShadow: network === n.key ? "0 0 0 3px rgba(0,212,170,0.12)" : undefined,
                    }}
                  >
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 12, fontWeight: 600, color: network === n.key ? "var(--accent)" : "var(--fg)" }}>{n.label}</span>
                    <span style={{ fontSize: 10, color: "var(--muted)" }}>{n.note}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12 }}>
              <label className="label" style={{ display: "flex", justifyContent: "space-between" }}>
                收款地址 <span style={{ color: "var(--tertiary)", fontWeight: 400 }}>地址前 4 后 4 脱敏展示</span>
              </label>
              <input
                className="input"
                style={{ height: 48, fontFamily: "var(--font-geist-mono), monospace" }}
                placeholder={net.placeholder}
                value={address}
                onChange={(e) => { setAddress(e.target.value); setErr(""); }}
              />
              {address && addrOk && <div style={{ fontSize: 12, color: "var(--success)" }}>✓ 地址格式校验通过</div>}
              {address && !addrOk && <div style={{ fontSize: 12, color: "var(--danger)" }}>地址格式不正确，请检查（{net.label}）</div>}
            </div>

            {/* 提交摘要 */}
            <div style={{ height: 1, background: "var(--rule)", margin: "16px 0 8px" }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0" }}>
              <span style={{ color: "var(--muted)" }}>提现金额</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{amt.toFixed(2)} USDT</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0" }}>
              <span style={{ color: "var(--muted)" }}>手续费</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600, color: "var(--danger)" }}>{feeUsdt.toFixed(2)} USDT</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0" }}>
              <span style={{ color: "var(--muted)" }}>实际到账</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600, color: "var(--success)" }}>{Math.max(amt - feeUsdt, 0).toFixed(2)} USDT</span>
            </div>
            <div style={{ height: 1, background: "var(--rule)", margin: "8px 0 16px" }} />

            <button className="btn btn-primary" style={{ width: "100%", height: 48, fontSize: 16 }} disabled={busy || !addrOk || !amountOk} onClick={openConfirm}>
              {busy ? "提交中…" : "提交提现申请"}
            </button>
            <div style={{ fontSize: 10, color: "var(--tertiary)", textAlign: "center", marginTop: 8 }}>
              提交后进入人工审核 · 通过后自动链上打款 · 到账时间取决于网络确认
            </div>
          </div>

          {/* 右：提现记录表 + 状态详情卡 */}
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>提现记录</div>
              <span className="panel-sub">WS · withdrawal.status 实时更新</span>
            </div>
            {records.length === 0 ? (
              <div className="empty-state" style={{ minHeight: 160 }}>
                <div className="es-ic">↗</div>
                <div style={{ fontSize: 13 }}>暂无提现记录</div>
              </div>
            ) : (
              <>
                <table className="ftx-table">
                  <thead>
                    <tr><th>单号</th><th className="num">金额</th><th>网络</th><th>状态</th></tr>
                  </thead>
                  <tbody>
                    {records.map((wd) => {
                      const st = WD_STATUS[wd.status] || { label: wd.status, cls: "badge-muted" };
                      const open = expandedId === wd.id;
                      return (
                        <tr key={wd.id} onClick={() => setExpandedId(open ? null : wd.id)} style={{ cursor: "pointer" }}>
                          <td className="num">#{wd.id}</td>
                          <td className="num">{wd.amount_usdt.toFixed(2)}</td>
                          <td>{NET_LABEL[wd.network] || wd.network}</td>
                          <td>
                            <span className={`badge ${st.cls}`}>{st.label}</span>
                            <span style={{ marginLeft: 6, fontSize: 10, color: "var(--tertiary)" }}>{open ? "收起" : "详情"}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* 状态详情卡（按状态着色） */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
                  {records.slice(0, 3).map((wd) => {
                    const st = WD_STATUS[wd.status] || { label: wd.status, cls: "badge-muted" };
                    const isRejected = wd.status === "rejected";
                    const isPaid = wd.status === "paid";
                    const detailOpen = expandedId === wd.id;
                    return (
                      <div
                        key={wd.id}
                        onClick={() => setExpandedId(detailOpen ? null : wd.id)}
                        style={{
                          border: isRejected ? "1px solid rgba(239,68,68,0.3)" : isPaid ? "1px solid rgba(40,196,100,0.3)" : "1px solid var(--rule)",
                          borderRadius: 6, padding: 12, cursor: "pointer",
                          background: isRejected ? "rgba(239,68,68,0.04)" : isPaid ? "rgba(40,196,100,0.04)" : undefined,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                          <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 12 }}>#{wd.id} · {wd.amount_usdt.toFixed(2)} USDT · {NET_LABEL[wd.network] || wd.network}</span>
                          <span className={`badge ${st.cls}`}>{st.label}</span>
                        </div>
                        <div style={{ fontSize: 12, color: "var(--muted)" }}>
                          {isRejected
                            ? <span style={{ color: "var(--danger)" }}>原因：{wd.reject_reason || "管理员未注明（如有疑问请联系客服）"}</span>
                            : isPaid
                              ? <>TxHash：<span style={{ color: "var(--accent)" }}>{(wd.tx_hash || "—").slice(0, 6)}…{(wd.tx_hash || "").slice(-4)}</span> · 链上已确认</>
                              : WD_MSG[wd.status] || "等待管理员审核"}
                        </div>
                        {detailOpen && (
                          <div style={{ borderTop: "1px solid var(--rule)", marginTop: 10, paddingTop: 10, fontSize: 12, display: "grid", gridTemplateColumns: "110px 1fr", gap: "6px 12px" }}>
                            <span style={{ color: "var(--muted)" }}>收款地址</span><span style={{ wordBreak: "break-all" }}>{wd.address}</span>
                            <span style={{ color: "var(--muted)" }}>申请金额</span><span>{wd.amount_usdt.toFixed(2)} USDT</span>
                            <span style={{ color: "var(--muted)" }}>手续费</span><span>{wd.fee_usdt.toFixed(2)} USDT</span>
                            <span style={{ color: "var(--muted)" }}>实发金额</span><span>{(wd.amount_usdt - wd.fee_usdt).toFixed(2)} USDT</span>
                            <span style={{ color: "var(--muted)" }}>提交时间</span><span>{wd.created_at ? new Date(wd.created_at).toLocaleString("zh-CN") : "—"}</span>
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
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 提交前二次确认弹窗 */}
      {confirmOpen && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.75)", backdropFilter: "blur(4px)", zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setConfirmOpen(false)}
        >
          <div
            style={{ width: 460, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 12, animation: "toastIn .22s ease" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>确认提交提现？</div>
              <button style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 16, cursor: "pointer", padding: 4 }} onClick={() => setConfirmOpen(false)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>提交后进入人工审核，无法撤回；驳回时资金自动退回可提现余额</div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0" }}>
              <span style={{ color: "var(--muted)" }}>提现金额</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{amt.toFixed(2)} USDT</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0" }}>
              <span style={{ color: "var(--muted)" }}>网络</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{net.label}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0" }}>
              <span style={{ color: "var(--muted)" }}>实际到账</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600, color: "var(--success)" }}>{Math.max(amt - feeUsdt, 0).toFixed(2)} USDT</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0" }}>
              <span style={{ color: "var(--muted)" }}>收款地址</span>
              <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600, fontSize: 11 }}>{addrMasked}</span>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setConfirmOpen(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={confirmSubmit} disabled={busy}>
                {busy ? "提交中…" : "确认提交"}
              </button>
            </div>
          </div>
        </div>
      )}

    </main>
  );
}
