"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Strategy = { id: number; display_name: string; style: string; risk_rating: string; status: string; followers: number; roi_30d: number; win_rate_all: number };
type Trader = { id: number; trader_id: string; name: string; roi_7d: number; roi_30d: number; roi_all: number; win_rate_all: number; max_drawdown: number; trading_days: number; followers: number };

/** M5 T5.4 策略管理：待选池 + 强制上架(G04 留痕) + 状态切换。 */
export default function AdminStrategiesPage() {
  const router = useRouter();
  const [listed, setListed] = useState<Strategy[]>([]);
  const [pending, setPending] = useState<Trader[]>([]);
  const [msg, setMsg] = useState("");
  const [forceTarget, setForceTarget] = useState<Trader | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [forceReason, setForceReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [l, p] = await Promise.all([
        apiFetch<{ items: Strategy[] }>("/admin/v1/signals", {}, tokenStore.adminAccess),
        apiFetch<{ items: Trader[] }>("/admin/v1/signals/pending", {}, tokenStore.adminAccess),
      ]);
      setListed(l.items);
      setPending(p.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function setStatus(s: Strategy, status: string) {
    try {
      await apiFetch(`/admin/v1/signals/${s.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }, tokenStore.adminAccess);
      setMsg(`「${s.display_name}」已${status === "paused" ? "暂停" : status === "delisted" ? "下架" : "恢复"}`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function doForceList() {
    if (!forceTarget) return;
    try {
      const r = await apiFetch<{ id: number }>("/admin/v1/signals", {
        method: "POST",
        body: JSON.stringify({ trader_id: forceTarget.id, display_name: displayName || forceTarget.trader_id, style: "trend", risk_rating: "mid", force: true, force_reason: forceReason }),
      }, tokenStore.adminAccess);
      setMsg(`已强制上架 #${r.id}（G04 留痕）`);
      setForceTarget(null);
      setForceReason("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "上架失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>策略管理（★G04）</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>待选池（{pending.length}）</div>
      <div className="card" style={{ overflowX: "auto", marginBottom: 20 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>ID</th><th style={th}>带单员</th><th style={th}>30日</th><th style={th}>累计</th><th style={th}>胜率</th><th style={th}>回撤</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={td}>{t.id}</td>
                <td style={{ ...td, fontWeight: 600 }}>{t.trader_id}</td>
                <td style={td}>{t.roi_30d.toFixed(1)}%</td>
                <td style={td}>{t.roi_all.toFixed(1)}%</td>
                <td style={td}>{t.win_rate_all.toFixed(1)}%</td>
                <td style={td}>{t.max_drawdown.toFixed(1)}%</td>
                <td style={td}>
                  <button className="btn btn-primary" style={{ padding: "5px 12px", fontSize: 12 }} onClick={() => { setForceTarget(t); setDisplayName(""); }}>上架</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>已添加（{listed.length}）</div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>名称</th><th style={th}>风格</th><th style={th}>30日</th><th style={th}>胜率</th><th style={th}>状态</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {listed.map((s) => (
              <tr key={s.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={{ ...td, fontWeight: 600 }}>{s.display_name}</td>
                <td style={td}>{s.style}</td>
                <td style={td}>{s.roi_30d.toFixed(1)}%</td>
                <td style={td}>{s.win_rate_all.toFixed(1)}%</td>
                <td style={td}>{s.status === "listed" ? <span style={{ color: "var(--success)" }}>运行中</span> : s.status === "paused" ? <span style={{ color: "var(--warning)" }}>已暂停</span> : <span style={{ color: "var(--muted)" }}>已下架</span>}</td>
                <td style={td}>
                  {s.status === "listed" ? (
                    <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12, marginRight: 6 }} onClick={() => setStatus(s, "paused")}>暂停</button>
                  ) : (
                    <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12, marginRight: 6 }} onClick={() => setStatus(s, "listed")}>恢复</button>
                  )}
                  <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12, color: "var(--danger)" }} onClick={() => setStatus(s, "delisted")}>下架</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {forceTarget && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 440, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>强制上架「{forceTarget.trader_id}」</div>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>
              胜率 {forceTarget.win_rate_all.toFixed(1)}% · 回撤 {forceTarget.max_drawdown.toFixed(1)}% · {forceTarget.trading_days} 天
            </div>
            <input className="input" style={{ width: "100%", marginBottom: 10 }} placeholder="展示名称" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            <input className="input" style={{ width: "100%", marginBottom: 16 }} placeholder="强制上架理由（必填，audit 留痕）" value={forceReason} onChange={(e) => setForceReason(e.target.value)} />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setForceTarget(null)}>取消</button>
              <button className="btn btn-primary" onClick={doForceList} disabled={!forceReason}>确认强制上架</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
