"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Summary = { total_usdt: number; available_usdt: number; withdrawing_usdt: number; paid_usdt: number; frozen_usdt: number };
type LedgerItem = { id: number; owner_id: number; owner_email: string; source_user_id: number; amount_usdt: number; status: string; status_label: string; created_at: string | null };

/** M5 钱包账本：★G12 全平台 5 字段 + 手动补发/扣除（高危写操作）。 */
export default function AdminWalletsPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [msg, setMsg] = useState("");
  const [adjust, setAdjust] = useState<{ mode: "credit" | "debit" } | null>(null);
  const [userId, setUserId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        apiFetch<Summary>("/admin/v1/wallets/summary", {}, tokenStore.adminAccess),
        apiFetch<{ items: LedgerItem[] }>("/admin/v1/wallets", {}, tokenStore.adminAccess),
      ]);
      setSummary(s);
      setLedger(l.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function submitAdjust() {
    const uid = parseInt(userId, 10);
    const amt = parseFloat(amount);
    if (!uid || !amt || amt <= 0 || !reason.trim()) {
      setMsg("请填写用户ID、金额与理由");
      return;
    }
    try {
      const signed = adjust?.mode === "debit" ? -amt : amt;
      await apiFetch("/admin/v1/wallets/adjust", { method: "POST", body: JSON.stringify({ user_id: uid, amount_usdt: signed, reason: reason.trim() }) }, tokenStore.adminAccess);
      setMsg(`已${adjust?.mode === "debit" ? "扣除" : "补发"} ${amt} USDT（用户 #${uid}）· 审计留痕`);
      setAdjust(null);
      setUserId(""); setAmount(""); setReason("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  const cards: Array<[string, number | undefined, string | undefined]> = [
    ["累计奖励", summary?.total_usdt, undefined],
    ["可提现", summary?.available_usdt, "success"],
    ["提现中", summary?.withdrawing_usdt, undefined],
    ["已提现", summary?.paid_usdt, undefined],
    ["冻结", summary?.frozen_usdt, "danger"],
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>钱包账本</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>5 字段流水（G12）· 手动补发为高危操作（强制审计）</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => setAdjust({ mode: "debit" })}>手动扣除</button>
          <button className="btn btn-primary" onClick={() => setAdjust({ mode: "credit" })}>手动补发</button>
        </div>
      </div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

      {/* ★ G12 5 字段 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 16 }}>
        {cards.map(([label, val, tone]) => (
          <div key={label as string} className="card" style={{ padding: 16 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>{label as string}</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6, color: tone === "success" ? "var(--success)" : tone === "danger" ? "var(--danger)" : "var(--fg)" }}>
              {(val ?? 0).toFixed(2)} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>USDT</span>
            </div>
          </div>
        ))}
      </div>

      {/* 手动补发/扣除弹窗 */}
      {adjust && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "grid", placeItems: "center", zIndex: 50 }}>
          <div className="card" style={{ width: 380, padding: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 16 }}>{adjust.mode === "debit" ? "手动扣除" : "手动补发"}（USDT）</div>
            <input className="input" style={{ width: "100%", marginBottom: 10 }} placeholder="用户 ID" type="number" value={userId} onChange={(e) => setUserId(e.target.value)} />
            <input className="input" style={{ width: "100%", marginBottom: 10 }} placeholder="金额（正数）" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <input className="input" style={{ width: "100%", marginBottom: 16 }} placeholder="操作理由（必填，审计留痕）" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setAdjust(null)}>取消</button>
              <button className="btn btn-primary" onClick={submitAdjust}>确认</button>
            </div>
          </div>
        </div>
      )}

      {/* 流水明细 */}
      <div className="card" style={{ overflowX: "auto" }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>奖励流水明细 <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>/admin/v1/wallets</span></div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>时间</th><th style={th}>用户</th><th style={th}>来源</th><th style={th}>金额</th><th style={th}>状态</th>
            </tr>
          </thead>
          <tbody>
            {ledger.map((l) => (
              <tr key={l.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>{l.created_at?.slice(0, 16) || "-"}</td>
                <td style={td}>{l.owner_email}</td>
                <td style={td}>{l.source_user_id === l.owner_id ? "手动调整" : "邀请奖励"}</td>
                <td style={{ ...td, fontWeight: 700, color: l.amount_usdt >= 0 ? "var(--success)" : "var(--danger)" }}>
                  {l.amount_usdt >= 0 ? "+" : ""}{l.amount_usdt.toFixed(2)}
                </td>
                <td style={td}>
                  <span style={{ color: l.status === "available" ? "var(--success)" : l.status === "frozen" || l.status === "canceled" ? "var(--danger)" : "var(--muted)" }}>{l.status_label}</span>
                </td>
              </tr>
            ))}
            {ledger.length === 0 && <tr><td colSpan={5} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无奖励流水</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };