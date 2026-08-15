"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useWsChannel } from "@/components/WsProvider";

type Bot = {
  id: number;
  strategy_id: number;
  strategy_name: string;
  exchange: string;
  amount_mode: string;
  fixed_amount_usdt: number | null;
  percent: number | null;
  leverage: number;
  margin_mode: string;
  max_total_position_usdt: number;
  virtual_locked_usdt: number;
  status: string;
  paper: boolean;
  pnl: { open_positions: number; total_notional_usdt: number; unrealized_pnl_usdt: number; realized_pnl_usdt: number };
};

type Position = { symbol: string; side: string; qty: number; entry_price: number; mark_price: number; unrealized_pnl: number };
type Order = { id: number; action: string; qty: number; status: string; failure_category: string | null; latency_ms: number };

/** M3 T3.9 我的跟单：机器人卡片（状态/盈亏/参数）+ 暂停恢复 + 持仓 + 最近订单。 */
export default function MyBotsPage() {
  const router = useRouter();
  const [bots, setBots] = useState<Bot[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  // ★ M6 删除机器人（双重确认）+ 修改配置
  const [deleteTarget, setDeleteTarget] = useState<Bot | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [configTarget, setConfigTarget] = useState<Bot | null>(null);
  const [cfgForm, setCfgForm] = useState({ percent: 20, leverage: 10, margin_mode: "isolated", max_total_position_usdt: 10000 });
  const [cfgMsg, setCfgMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: Bot[] }>("/v1/bots", {}, tokenStore.access);
      setBots(r.items);
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

  // ── WS 实时：bot.position 仓位变化（更新保证金占用）──
  useWsChannel("bot.position", (raw) => {
    const payload = raw as { bot_id?: number; virtual_locked_usdt?: number; action?: string };
    if (!payload?.bot_id) return;
    setBots((bs) =>
      bs.map((b) =>
        b.id === payload.bot_id && payload.virtual_locked_usdt != null
          ? { ...b, virtual_locked_usdt: payload.virtual_locked_usdt! }
          : b
      )
    );
  });

  // ── WS 实时：account.balance 余额变动（奖励到账/解锁 → 刷新列表）──
  useWsChannel("account.balance", () => {
    load();
  });

  async function onStatus(bot: Bot, status: string) {
    try {
      await apiFetch(`/v1/bots/${bot.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }, tokenStore.access);
      setMsg(`「${bot.strategy_name}」已${status === "paused" ? "暂停" : "恢复"}`);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function onDelete() {
    if (!deleteTarget) return;
    try {
      await apiFetch(`/v1/bots/${deleteTarget.id}`, { method: "DELETE" }, tokenStore.access);
      setMsg(`「${deleteTarget.strategy_name}」已删除`);
      setDeleteTarget(null);
      setConfirmText("");
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "删除失败");
    }
  }

  function openConfig(bot: Bot) {
    setCfgForm({
      percent: bot.percent ?? 20,
      leverage: bot.leverage,
      margin_mode: bot.margin_mode,
      max_total_position_usdt: bot.max_total_position_usdt,
    });
    setCfgMsg("");
    setConfigTarget(bot);
  }

  async function onSaveConfig() {
    if (!configTarget) return;
    setCfgMsg("");
    try {
      await apiFetch(
        `/v1/bots/${configTarget.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            percent: cfgForm.percent,
            leverage: cfgForm.leverage,
            margin_mode: cfgForm.margin_mode,
            max_total_position_usdt: cfgForm.max_total_position_usdt,
          }),
        },
        tokenStore.access
      );
      setMsg(`「${configTarget.strategy_name}」配置已更新`);
      setConfigTarget(null);
      load();
    } catch (e) {
      setCfgMsg(e instanceof Error ? e.message : "保存失败");
    }
  }

  async function onExpand(bot: Bot) {
    if (expanded === bot.id) {
      setExpanded(null);
      return;
    }
    setExpanded(bot.id);
    setLoadingDetail(true);
    try {
      const [p, o] = await Promise.all([
        apiFetch<{ items: Position[] }>(`/v1/bots/${bot.id}/positions`, {}, tokenStore.access),
        apiFetch<{ items: Order[] }>(`/v1/bots/${bot.id}/orders`, {}, tokenStore.access),
      ]);
      setPositions(p.items);
      setOrders(o.items);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "详情加载失败");
    } finally {
      setLoadingDetail(false);
    }
  }

  // ★ 顶部统计条：聚合所有机器人的 pnl
  const stats = bots.reduce(
    (acc, b) => {
      acc.running += b.status === "active" ? 1 : 0;
      acc.positions += b.pnl.open_positions;
      acc.unrealized += b.pnl.unrealized_pnl_usdt;
      acc.realized += b.pnl.realized_pnl_usdt;
      return acc;
    },
    { running: 0, positions: 0, unrealized: 0, realized: 0 }
  );

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>我的跟单</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>跟单机器人管理 · 独立虚拟账本</div>
        </div>

        {/* ★ 统计条 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>运行中机器人</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4 }}>{stats.running}<span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}> / {bots.length}</span></div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>当前持仓</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4 }}>{stats.positions}</div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>未实现盈亏</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4, color: stats.unrealized >= 0 ? "var(--success)" : "var(--danger)" }}>
              {stats.unrealized >= 0 ? "+" : ""}{stats.unrealized.toFixed(2)} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>USDT</span>
            </div>
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>已实现盈亏</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 4, color: stats.realized >= 0 ? "var(--success)" : "var(--danger)" }}>
              {stats.realized >= 0 ? "+" : ""}{stats.realized.toFixed(2)} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>USDT</span>
            </div>
          </div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {bots.length === 0 ? (
          <div className="card" style={{ textAlign: "center", padding: 48, color: "var(--muted)" }}>
            还没有跟单机器人，去<Link href="/strategies" style={{ color: "var(--accent)", margin: "0 4px" }}>策略广场</Link>选择一个策略开始跟单
          </div>
        ) : (
          bots.map((bot) => (
            <div key={bot.id} className="card" style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>
                    {bot.strategy_name}
                    {bot.paper && (
                      <span style={{ fontSize: 11, color: "var(--accent)", background: "var(--accent-soft)", padding: "2px 8px", borderRadius: 12, marginLeft: 8, verticalAlign: "middle" }}>
                        模拟盘
                      </span>
                    )}
                  </div>
                  <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>
                    {bot.exchange} · {bot.margin_mode === "isolated" ? "逐仓" : "全仓"} {bot.leverage}x ·{" "}
                    {bot.amount_mode === "fixed" ? `固定 ${bot.fixed_amount_usdt} USDT` : `比例 ${bot.percent}%`}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span
                    style={{
                      fontSize: 12, padding: "4px 12px", borderRadius: 20,
                      background: bot.status === "active" ? "rgba(40,196,100,.15)" : "rgba(234,179,8,.12)",
                      color: bot.status === "active" ? "var(--success)" : "var(--warning)",
                    }}
                  >
                    {bot.status === "active" ? "运行中" : bot.status === "paused" ? "已暂停" : "已停止"}
                  </span>
                  {bot.status === "active" ? (
                    <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => onStatus(bot, "paused")}>暂停</button>
                  ) : (
                    <button className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => onStatus(bot, "active")}>恢复</button>
                  )}
                  <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => onExpand(bot)}>
                    {expanded === bot.id ? "收起" : "详情"}
                  </button>
                  <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => openConfig(bot)}>配置</button>
                  <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12, color: "var(--danger)", borderColor: "rgba(239,68,68,0.4)" }} onClick={() => { setConfirmText(""); setDeleteTarget(bot); }}>删除</button>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, fontSize: 13 }}>
                <div><span style={{ color: "var(--muted)" }}>持仓数</span><br /><strong>{bot.pnl.open_positions}</strong></div>
                <div><span style={{ color: "var(--muted)" }}>名义价值</span><br /><strong>{bot.pnl.total_notional_usdt.toFixed(2)} USDT</strong></div>
                <div><span style={{ color: "var(--muted)" }}>未实现盈亏</span><br /><strong style={{ color: bot.pnl.unrealized_pnl_usdt >= 0 ? "var(--success)" : "var(--danger)" }}>{bot.pnl.unrealized_pnl_usdt.toFixed(2)} USDT</strong></div>
                <div><span style={{ color: "var(--muted)" }}>已用保证金</span><br /><strong>{bot.virtual_locked_usdt.toFixed(2)} USDT</strong></div>
              </div>

              {expanded === bot.id && (
                <div style={{ marginTop: 16, borderTop: "1px solid var(--rule)", paddingTop: 16 }}>
                  {loadingDetail ? (
                    <div style={{ color: "var(--muted)", fontSize: 13 }}>加载中…</div>
                  ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>当前持仓</div>
                        {positions.length === 0 ? (
                          <div style={{ color: "var(--muted)", fontSize: 12 }}>暂无持仓</div>
                        ) : (
                          positions.map((p) => (
                            <div key={p.symbol} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--rule)" }}>
                              <span>{p.symbol} <span style={{ color: p.side === "long" ? "var(--success)" : "var(--danger)" }}>{p.side === "long" ? "多" : "空"}</span></span>
                              <span>{p.qty} @ {p.entry_price}</span>
                              <span style={{ color: p.unrealized_pnl >= 0 ? "var(--success)" : "var(--danger)" }}>{p.unrealized_pnl.toFixed(2)}</span>
                            </div>
                          ))
                        )}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>最近订单</div>
                        {orders.length === 0 ? (
                          <div style={{ color: "var(--muted)", fontSize: 12 }}>暂无订单</div>
                        ) : (
                          orders.map((o) => (
                            <div key={o.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--rule)" }}>
                              <span>{o.action.toUpperCase()} {o.qty}</span>
                              <span>{o.status === "filled" ? `成交 (${o.latency_ms}ms)` : `失败: ${o.failure_category || "?"}`}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* ★ M6 删除机器人：双重确认（需输入机器人名称） */}
      {deleteTarget && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 400, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "var(--danger)", marginBottom: 8 }}>删除跟单机器人</div>
            <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 6 }}>
              即将删除「{deleteTarget.strategy_name}」。删除后该策略的跟单将立即停止，持仓与历史订单记录将被移除，此操作不可恢复。
            </div>
            <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 12 }}>
              请输入机器人名称 <strong style={{ color: "var(--fg)" }}>{deleteTarget.strategy_name}</strong> 以确认：
            </div>
            <input
              className="input"
              style={{ width: "100%", marginBottom: 16 }}
              placeholder={deleteTarget.strategy_name}
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => { setDeleteTarget(null); setConfirmText(""); }}>取消</button>
              <button
                className="btn btn-primary"
                style={{ background: "var(--danger)", color: "#fff", opacity: confirmText === deleteTarget.strategy_name ? 1 : 0.5, cursor: confirmText === deleteTarget.strategy_name ? "pointer" : "not-allowed" }}
                disabled={confirmText !== deleteTarget.strategy_name}
                onClick={onDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ★ M6 修改机器人配置 */}
      {configTarget && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 420, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>修改「{configTarget.strategy_name}」配置</div>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>修改后立即生效，适用于后续新开仓位</div>
            <label className="label">跟单比例（%）</label>
            <input className="input" style={{ width: "100%", marginBottom: 12 }} type="number" min={1} max={100} value={cfgForm.percent} onChange={(e) => setCfgForm({ ...cfgForm, percent: Number(e.target.value) })} />
            <label className="label">杠杆（1-125x）</label>
            <input className="input" style={{ width: "100%", marginBottom: 12 }} type="number" min={1} max={125} value={cfgForm.leverage} onChange={(e) => setCfgForm({ ...cfgForm, leverage: Number(e.target.value) })} />
            <label className="label">保证金模式</label>
            <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
              {(["isolated", "cross"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setCfgForm({ ...cfgForm, margin_mode: m })}
                  style={{
                    flex: 1, padding: "8px 0", borderRadius: 6, fontSize: 13, cursor: "pointer",
                    border: cfgForm.margin_mode === m ? "1px solid var(--accent)" : "1px solid var(--rule)",
                    background: cfgForm.margin_mode === m ? "var(--accent-soft)" : "transparent",
                    color: cfgForm.margin_mode === m ? "var(--accent)" : "var(--muted)",
                  }}
                >
                  {m === "isolated" ? "逐仓" : "全仓"}
                </button>
              ))}
            </div>
            <label className="label">单笔最大名义价值（USDT）</label>
            <input className="input" style={{ width: "100%", marginBottom: 12 }} type="number" min={1} value={cfgForm.max_total_position_usdt} onChange={(e) => setCfgForm({ ...cfgForm, max_total_position_usdt: Number(e.target.value) })} />
            {cfgMsg && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 8 }}>{cfgMsg}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setConfigTarget(null)}>取消</button>
              <button className="btn btn-primary" onClick={onSaveConfig}>保存配置</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
