"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useWsChannel } from "@/components/WsProvider";
import { localDate } from "@/lib/time";

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

const STATUS_META: Record<string, { label: string; color: string }> = {
  active: { label: "运行中", color: "#28c464" },
  paused: { label: "已暂停", color: "#eab308" },
  stopped: { label: "已停止", color: "#ef4444" },
};

function fmtNum(n: number, digits = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** M3 T3.9 我的跟单（对齐设计稿）：页头「查看策略+新增跟单」+ 指标条 + 订阅过期横幅 +
 *  机器人卡片（编号/状态呼吸圆点/2×2 参数网格/spark+操作按钮组）+ 暂停/恢复确认弹窗 +
 *  空态引导卡。保留展开详情、WS 实时、删除需输名称、修改配置（含固定金额/比例）等增强。 */
export default function MyBotsPage() {
  const router = useRouter();
  const [bots, setBots] = useState<Bot[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [orderFills, setOrderFills] = useState<Record<number, number>>({});
  // 订阅状态（G10 过期横幅）
  const [sub, setSub] = useState<{ active: boolean; expires_at?: string } | null>(null);
  // ★ 暂停 / 恢复确认弹窗
  const [pauseTarget, setPauseTarget] = useState<Bot | null>(null);
  const [resumeTarget, setResumeTarget] = useState<Bot | null>(null);
  // ★ M6 删除机器人（双重确认，需输入机器人名称）+ 修改配置
  const [deleteTarget, setDeleteTarget] = useState<Bot | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [configTarget, setConfigTarget] = useState<Bot | null>(null);
  const [cfgForm, setCfgForm] = useState({
    amount_mode: "percent" as "fixed" | "percent",
    percent: 20,
    fixed_amount_usdt: 500,
    leverage: 10,
    margin_mode: "isolated",
    max_total_position_usdt: 10000,
  });
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
    apiFetch<{ active: boolean; expires_at?: string }>("/v1/subscriptions/me", {}, tokenStore.access)
      .then((d) => setSub(d))
      .catch(() => setSub(null));
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
      setPauseTarget(null);
      setResumeTarget(null);
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
      amount_mode: bot.amount_mode === "fixed" ? "fixed" : "percent",
      percent: bot.percent ?? 20,
      fixed_amount_usdt: bot.fixed_amount_usdt ?? 500,
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
            amount_mode: cfgForm.amount_mode,
            percent: cfgForm.amount_mode === "percent" ? cfgForm.percent : null,
            fixed_amount_usdt: cfgForm.amount_mode === "fixed" ? cfgForm.fixed_amount_usdt : null,
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
      setPositions([]);
      setOrders([]);
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
      setOrderFills((prev) => ({ ...prev, [bot.id]: o.items.filter((x) => x.status === "filled").length }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "详情加载失败");
    } finally {
      setLoadingDetail(false);
    }
  }

  /** 方向：展开且已加载持仓时按净持仓推断，否则显示「跟随信号」。 */
  function botDirection(bot: Bot): { text: string; color: string } {
    if (expanded === bot.id && positions.length > 0) {
      const long = positions.filter((p) => p.side === "long").reduce((s, p) => s + p.qty, 0);
      const short = positions.filter((p) => p.side === "short").reduce((s, p) => s + p.qty, 0);
      if (long > short) return { text: "做多", color: "var(--success)" };
      if (short > long) return { text: "做空", color: "var(--danger)" };
    }
    return { text: "跟随信号", color: "var(--muted)" };
  }

  // ★ 顶部指标条：聚合所有机器人的 pnl
  const stats = bots.reduce(
    (acc, b) => {
      acc.running += b.status === "active" ? 1 : 0;
      acc.paused += b.status === "paused" ? 1 : 0;
      acc.positions += b.pnl.open_positions;
      acc.unrealized += b.pnl.unrealized_pnl_usdt;
      acc.realized += b.pnl.realized_pnl_usdt;
      acc.locked += b.virtual_locked_usdt;
      return acc;
    },
    { running: 0, paused: 0, positions: 0, unrealized: 0, realized: 0, locked: 0 }
  );

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <style>{`
        @keyframes saasPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        .saas-bcard { transition: box-shadow .2s, border-color .2s; }
        .saas-bcard:hover { border-color: rgba(100,116,139,.55); box-shadow: 0 8px 24px rgba(0,0,0,.35); }
      `}</style>

      <div className="page-wrap">
        {/* 页头（设计稿：eyebrow + 标题 + 查看策略/新增跟单） */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">MY COPY BOTS · 我的跟单</div>
            <h1 className="page-title">
              我的跟单管理<small>独立机器人 · 实时同步交易所</small>
            </h1>
          </div>
          <div className="page-actions">
            <Link href="/strategies" className="btn btn-secondary">查看策略</Link>
            <Link href="/strategies" className="btn btn-primary">＋ 新增跟单</Link>
          </div>
        </div>

        {/* 指标条 */}
        <div className="kpi-grid" style={{ marginBottom: 16 }}>
          <div className="kpi-card">
            <div className="kpi-l">运行中机器人</div>
            <div className="kpi-v">{stats.running}<span style={{ fontSize: 13, fontWeight: 400, color: "var(--muted)" }}> / {bots.length}</span></div>
            <div className="kpi-s">{stats.paused} 个已暂停</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">当前持仓</div>
            <div className="kpi-v">{stats.positions}</div>
            <div className="kpi-s">全部机器人持仓</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">已实现盈亏</div>
            <div className="kpi-v" style={{ color: stats.realized >= 0 ? "var(--success)" : "var(--danger)" }}>
              {stats.realized >= 0 ? "+" : ""}{fmtNum(stats.realized)}
            </div>
            <div className="kpi-s">USDT · 含手续费</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">未实现盈亏</div>
            <div className="kpi-v" style={{ color: stats.unrealized >= 0 ? "var(--success)" : "var(--danger)" }}>
              {stats.unrealized >= 0 ? "+" : ""}{fmtNum(stats.unrealized)}
            </div>
            <div className="kpi-s">USDT · WS 实时推送</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">占用保证金</div>
            <div className="kpi-v">{fmtNum(stats.locked)}</div>
            <div className="kpi-s">USDT · 全部机器人</div>
          </div>
        </div>

        {/* 订阅过期横幅（G10：已过期可平仓不可开仓 + 续费链接） */}
        {sub && !sub.active && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: 8, border: "1px solid rgba(234,179,8,0.35)", background: "rgba(234,179,8,0.07)", fontSize: 12, color: "var(--warning)", marginBottom: 16, flexWrap: "wrap" }}>
            <span>⚠</span>
            <span>
              订阅未开通或已过期{sub.expires_at ? `（${localDate(sub.expires_at) ?? "—"}）` : ""} · <strong style={{ color: "var(--warning)" }}>跟单已暂停开仓，已有持仓可正常平仓</strong>。请尽快{" "}
              <Link href="/subscriptions" style={{ color: "var(--warning)", textDecoration: "underline" }}>续费</Link> 恢复跟单。
            </span>
          </div>
        )}

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {bots.length === 0 ? (
          /* 空态引导卡 */
          <div className="empty-state" style={{ marginTop: 8 }}>
            <div className="es-ic">＋</div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>开启新的跟单</div>
              <div style={{ fontSize: 12, color: "var(--muted)", maxWidth: 260, margin: "0 auto" }}>从策略广场挑选策略，配置方向与杠杆，一键跟单</div>
            </div>
            <Link href="/strategies" className="btn btn-primary">去策略广场</Link>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 16, alignItems: "stretch" }}>
            {bots.map((bot) => {
              const sm = STATUS_META[bot.status] ?? STATUS_META.stopped;
              const dir = botDirection(bot);
              return (
                <div
                  key={bot.id}
                  className="card saas-bcard"
                  style={{
                    padding: 20, display: "flex", flexDirection: "column", gap: 16, position: "relative", overflow: "hidden",
                    opacity: bot.status === "stopped" ? 0.72 : 1,
                  }}
                >
                  {/* 卡头：名称 + 机器人编号 + 状态呼吸圆点 */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 15, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      {bot.strategy_name}
                      {bot.paper && (
                        <span style={{ fontSize: 11, color: "var(--accent)", background: "var(--accent-soft)", padding: "2px 8px", borderRadius: 12 }}>模拟盘</span>
                      )}
                      <span style={{ fontFamily: "var(--font-geist-mono)", fontSize: 10, color: "var(--tertiary)", fontWeight: 400 }}>#{String(bot.id).padStart(4, "0")}</span>
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                      <span
                        style={{
                          width: 8, height: 8, borderRadius: "50%", background: sm.color, boxShadow: `0 0 8px ${sm.color}`,
                          animation: bot.status === "active" ? "saasPulse 2s infinite" : "none",
                        }}
                      />
                      {sm.label}
                    </span>
                  </div>

                  {/* 2×2 参数网格：方向/杠杆/保证金模式/跟单比例/名义价值/已实现盈亏/未实现盈亏/今日成交 */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px" }}>
                    {[
                      ["方向", dir.text, dir.color],
                      ["杠杆", `${bot.leverage}×`, undefined],
                      ["保证金模式", bot.margin_mode === "isolated" ? "逐仓" : "全仓", undefined],
                      ["跟单比例", bot.amount_mode === "fixed" ? `${fmtNum(bot.fixed_amount_usdt ?? 0)} USDT` : `${bot.percent ?? 0}%`, undefined],
                      ["名义价值", `${fmtNum(bot.pnl.total_notional_usdt)} USDT`, undefined],
                      ["已实现盈亏", `${bot.pnl.realized_pnl_usdt >= 0 ? "+" : ""}${fmtNum(bot.pnl.realized_pnl_usdt)}`, bot.pnl.realized_pnl_usdt >= 0 ? "var(--success)" : "var(--danger)"],
                      ["未实现盈亏", `${bot.pnl.unrealized_pnl_usdt >= 0 ? "+" : ""}${fmtNum(bot.pnl.unrealized_pnl_usdt)}`, bot.pnl.unrealized_pnl_usdt >= 0 ? "var(--success)" : "var(--danger)"],
                      ["今日成交", orderFills[bot.id] != null ? `${orderFills[bot.id]} 笔` : "—", undefined],
                    ].map(([k, v, c]) => (
                      <div key={k as string}>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{k}</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600, marginTop: 2, color: (c as string) ?? "var(--fg)" }}>{v}</div>
                      </div>
                    ))}
                  </div>

                  {/* 底部：总盈亏 + 操作按钮组 */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, paddingTop: 12, borderTop: "1px solid rgba(51,65,85,0.4)", flexWrap: "wrap" }}>
                    <div style={{ flex: 1, minWidth: 90 }}>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>总盈亏（已实现+未实现）</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 14, fontWeight: 700, color: bot.pnl.realized_pnl_usdt + bot.pnl.unrealized_pnl_usdt >= 0 ? "var(--success)" : "var(--danger)" }}>
                        {bot.pnl.realized_pnl_usdt + bot.pnl.unrealized_pnl_usdt >= 0 ? "+" : ""}
                        {fmtNum(bot.pnl.realized_pnl_usdt + bot.pnl.unrealized_pnl_usdt)} USDT
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {bot.status === "active" && (
                        <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => setPauseTarget(bot)}>暂停</button>
                      )}
                      {bot.status === "paused" && (
                        <button className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => setResumeTarget(bot)}>恢复</button>
                      )}
                      {bot.status === "stopped" && (
                        <button
                          className="btn btn-secondary"
                          style={{ padding: "6px 14px", fontSize: 12 }}
                          onClick={() => {
                            if (sub && !sub.active) {
                              setErr("订阅未开通或已过期，无法重新开启");
                            } else {
                              onStatus(bot, "active");
                            }
                          }}
                        >
                          重新开启
                        </button>
                      )}
                      <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => openConfig(bot)}>修改配置</button>
                      <button className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => onExpand(bot)}>
                        {expanded === bot.id ? "收起" : "详情"}
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "6px 14px", fontSize: 12, color: "var(--danger)", borderColor: "rgba(239,68,68,0.4)" }}
                        onClick={() => { setConfirmText(""); setDeleteTarget(bot); }}
                      >
                        删除
                      </button>
                    </div>
                  </div>

                  {/* 展开详情：持仓 + 最近订单（保留增强） */}
                  {expanded === bot.id && (
                    <div style={{ marginTop: 4, borderTop: "1px solid var(--rule)", paddingTop: 16 }}>
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
                                <div key={p.symbol} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--rule)" }}>
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
                                <div key={o.id} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--rule)" }}>
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
              );
            })}

            {/* 空态引导卡（网格尾部） */}
            <Link
              href="/strategies"
              style={{
                border: "1px dashed var(--rule)", borderRadius: 10, minHeight: 180, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 10, textDecoration: "none", color: "var(--muted)",
              }}
            >
              <div style={{ width: 48, height: 48, borderRadius: "50%", border: "1px dashed var(--tertiary)", display: "grid", placeItems: "center", fontSize: 20 }}>＋</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>开启新的跟单</div>
              <div style={{ fontSize: 11 }}>从策略广场挑选策略，一键跟单</div>
            </Link>
          </div>
        )}
      </div>

      {/* 暂停确认弹窗（非破坏性说明） */}
      {pauseTarget && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", backdropFilter: "blur(4px)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) setPauseTarget(null); }}
        >
          <div style={{ width: 480, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>暂停跟单机器人？</div>
              <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setPauseTarget(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.8 }}>
              <strong style={{ color: "var(--fg)" }}>{pauseTarget.strategy_name}</strong> 暂停后不再开新仓，<strong style={{ color: "var(--fg)" }}>已有持仓不受影响，仍可平仓</strong>。可随时恢复。
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 6, background: "rgba(40,196,100,0.08)", border: "1px solid rgba(40,196,100,0.3)", fontSize: 12, color: "var(--success)" }}>
              <span>✓</span>
              <span>暂停为非破坏性操作，持仓与收益均保留</span>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setPauseTarget(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => onStatus(pauseTarget, "paused")}>确认暂停</button>
            </div>
          </div>
        </div>
      )}

      {/* 恢复确认弹窗（校验订阅/API/风控说明） */}
      {resumeTarget && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", backdropFilter: "blur(4px)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) setResumeTarget(null); }}
        >
          <div style={{ width: 480, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid rgba(234,179,8,0.4)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>恢复跟单机器人？</div>
              <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setResumeTarget(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.8 }}>
              <strong style={{ color: "var(--fg)" }}>{resumeTarget.strategy_name}</strong> 恢复后将立即重新同步信号并开始跟单。
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 6, background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: 12, color: "var(--warning)" }}>
              <span>⚠</span>
              <span>恢复前将校验：订阅状态 · API 权限 · 风控白名单</span>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setResumeTarget(null)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => onStatus(resumeTarget, "active")}>确认恢复</button>
            </div>
          </div>
        </div>
      )}

      {/* M6 修改机器人配置（含固定金额/比例） */}
      {configTarget && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) setConfigTarget(null); }}
        >
          <div style={{ width: 460, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>修改「{configTarget.strategy_name}」配置</div>
              <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setConfigTarget(null)}>✕</button>
            </div>
            <div style={{ color: "var(--muted)", fontSize: 12 }}>修改后立即生效，适用于后续新开仓位</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="label">杠杆（1-125x）</label>
                <input className="input" type="number" min={1} max={125} value={cfgForm.leverage} onChange={(e) => setCfgForm({ ...cfgForm, leverage: Number(e.target.value) })} />
              </div>
              <div>
                <label className="label">保证金模式</label>
                <select className="input" value={cfgForm.margin_mode} onChange={(e) => setCfgForm({ ...cfgForm, margin_mode: e.target.value })}>
                  <option value="isolated">逐仓</option>
                  <option value="cross">全仓</option>
                </select>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="label">跟单比例方式</label>
                <select className="input" value={cfgForm.amount_mode} onChange={(e) => setCfgForm({ ...cfgForm, amount_mode: e.target.value as "fixed" | "percent" })}>
                  <option value="percent">按比例</option>
                  <option value="fixed">固定金额</option>
                </select>
              </div>
              <div>
                <label className="label">{cfgForm.amount_mode === "fixed" ? "固定金额（USDT）" : "跟单比例（%）"}</label>
                {cfgForm.amount_mode === "fixed" ? (
                  <input className="input" type="number" min={1} value={cfgForm.fixed_amount_usdt} onChange={(e) => setCfgForm({ ...cfgForm, fixed_amount_usdt: Number(e.target.value) })} />
                ) : (
                  <input className="input" type="number" min={1} max={100} value={cfgForm.percent} onChange={(e) => setCfgForm({ ...cfgForm, percent: Number(e.target.value) })} />
                )}
              </div>
            </div>
            <div>
              <label className="label">单笔最大名义价值（USDT）</label>
              <input className="input" type="number" min={1} value={cfgForm.max_total_position_usdt} onChange={(e) => setCfgForm({ ...cfgForm, max_total_position_usdt: Number(e.target.value) })} />
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 6, background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: 12, color: "var(--warning)" }}>
              <span>⚠</span>
              <span>修改杠杆/保证金模式将同步至交易所，已有持仓不追溯</span>
            </div>
            {cfgMsg && <div style={{ color: "var(--danger)", fontSize: 13 }}>{cfgMsg}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 6 }}>
              <button className="btn btn-secondary" onClick={() => setConfigTarget(null)}>取消</button>
              <button className="btn btn-primary" onClick={onSaveConfig}>保存配置</button>
            </div>
          </div>
        </div>
      )}

      {/* M6 删除机器人：双重确认（需输入机器人名称） */}
      {deleteTarget && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) { setDeleteTarget(null); setConfirmText(""); } }}
        >
          <div style={{ width: 440, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: "var(--danger)" }}>删除跟单机器人？</div>
              <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => { setDeleteTarget(null); setConfirmText(""); }}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.8 }}>
              即将删除「<strong style={{ color: "var(--danger)" }}>{deleteTarget.strategy_name}</strong>」。删除后该策略的跟单将立即停止，持仓与历史订单记录将被移除，此操作<strong style={{ color: "var(--danger)" }}>不可恢复</strong>。
            </div>
            <div>
              <label className="label">请输入机器人名称确认：<strong style={{ color: "var(--fg)" }}>{deleteTarget.strategy_name}</strong></label>
              <input
                className="input"
                placeholder={deleteTarget.strategy_name}
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => { setDeleteTarget(null); setConfirmText(""); }}>取消</button>
              <button
                className="btn btn-primary"
                style={{ flex: 1, background: "var(--danger)", color: "#fff", opacity: confirmText === deleteTarget.strategy_name ? 1 : 0.5, cursor: confirmText === deleteTarget.strategy_name ? "pointer" : "not-allowed" }}
                disabled={confirmText !== deleteTarget.strategy_name}
                onClick={onDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
