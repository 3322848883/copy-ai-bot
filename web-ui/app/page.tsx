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

type Order = {
  id: number;
  bot_id: number;
  strategy_name: string | null;
  action: string;
  qty: number;
  status: string;
  failure_category: string | null;
  latency_ms: number | null;
  executed_at: string | null;
};

type Ticker = { symbol: string; price: number; change_pct: number };

type Dashboard = {
  metrics: {
    available_usdt: number;
    total_reward_usdt: number;
    running_bots: number;
    total_bots: number;
    total_pnl_usdt: number;
    subscription: { active: boolean; plan_id?: string; expires_at?: string; days_left?: number };
  };
  onboarding: { has_api: boolean; has_bot: boolean; step: number };
  bots: Bot[];
  recent_orders: Order[];
  tickers: Ticker[];
};

const ACTION_LABEL: Record<string, string> = { open: "开仓", add: "加仓", reduce: "减仓", close: "平仓" };
const ACTION_COLOR: Record<string, string> = { open: "var(--success)", add: "var(--success)", reduce: "var(--danger)", close: "var(--danger)" };

function fmt(n: number, digits = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** M6 P0：首页数据看板（4 指标卡 + G22 眼睛 + G23 引导 + 跟单入口 + WS 实时）。 */
export default function Home() {
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [err, setErr] = useState("");
  const [masked, setMasked] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; type: string; msg: string }[]>([]);

  const load = useCallback(async () => {
    try {
      const d = await apiFetch<Dashboard>("/v1/dashboard", {}, tokenStore.access);
      setData(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.replace("/login");
      return;
    }
    load();
  }, [load, router]);

  const pushToast = useCallback((type: string, msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, type, msg }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  // ── WS 实时：pnl.tick 更新机器人盈亏 ──
  useWsChannel("pnl.tick", (raw) => {
    const payload = raw as { bots?: { bot_id: number; unrealized_pnl_usdt: number }[]; total_unrealized_pnl_usdt?: number };
    if (!payload?.bots) return;
    setData((d) => {
      if (!d) return d;
      const byId = new Map(payload.bots!.map((b) => [b.bot_id, b.unrealized_pnl_usdt]));
      return {
        ...d,
        metrics: {
          ...d.metrics,
          total_pnl_usdt: payload.total_unrealized_pnl_usdt ?? d.metrics.total_pnl_usdt,
        },
        bots: d.bots.map((b) => (byId.has(b.id) ? { ...b, pnl: { ...b.pnl, unrealized_pnl_usdt: byId.get(b.id)! } } : b)),
      };
    });
  });

  // ── WS 实时：bot.position 仓位变化（更新保证金占用）──
  useWsChannel("bot.position", (raw) => {
    const payload = raw as { bot_id?: number; virtual_locked_usdt?: number; action?: string };
    if (!payload?.bot_id) return;
    setData((d) => {
      if (!d) return d;
      return {
        ...d,
        bots: d.bots.map((b) =>
          b.id === payload.bot_id && payload.virtual_locked_usdt != null
            ? { ...b, virtual_locked_usdt: payload.virtual_locked_usdt! }
            : b
        ),
      };
    });
  });

  // ── WS 实时：reward.tick 奖励到账 ──
  useWsChannel("reward.tick", (raw) => {
    const payload = raw as { amount_usdt?: number; status?: string };
    pushToast("success", `奖励已到账 +${fmt(payload.amount_usdt ?? 0)} USDT（WS reward.tick）`);
    load();
  });

  // ── WS 实时：bot.order 下单结果 ──
  useWsChannel("bot.order", (raw) => {
    const payload = raw as { action?: string; symbol?: string; status?: string; failure_category?: string | null };
    const act = payload.action ? ACTION_LABEL[payload.action] ?? payload.action : "";
    const ok = payload.status === "filled";
    pushToast(
      ok ? "success" : "error",
      ok ? `${payload.symbol} ${act} 已成交（WS bot.order）` : `${payload.symbol} ${act} 失败：${payload.failure_category ?? "?"}`
    );
    load();
  });

  // ── WS 实时：withdrawal.status 提现状态 ──
  useWsChannel("withdrawal.status", (raw) => {
    const payload = raw as { withdrawal_id?: number; amount_usdt?: number; status?: string };
    pushToast("info", `提现单 #${payload.withdrawal_id} 状态更新：${payload.status}`);
    load();
  });

  const onboarding = data?.onboarding;

  // 新手引导步骤状态（G23：has_api + has_bot 时隐藏）
  const showOnboard = onboarding && (!onboarding.has_api || !onboarding.has_bot);

  const totalPnl = data?.metrics?.total_pnl_usdt ?? 0;

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "40px 24px 64px", position: "relative", zIndex: 1 }}>
        {/* 页头 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 11, fontFamily: "var(--font-geist-mono)", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent)", marginBottom: 6 }}>
              DASHBOARD
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 700 }}>
              首页数据看板
              <small style={{ fontSize: 12, color: "var(--muted)", fontWeight: 400, marginLeft: 10, fontFamily: "var(--font-geist-mono)" }}>
                已同步 · 实时推送
              </small>
            </h1>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn btn-secondary" onClick={load}>刷新数据</button>
            <Link href="/strategies" className="btn btn-primary">去策略广场</Link>
          </div>
        </div>

        {err && <div className="error-box">{err}</div>}

        {!data ? (
          <div style={{ display: "grid", gap: 12 }}>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="card" style={{ height: 90, opacity: 0.4, background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent)", animation: "shimmer 1.4s infinite" }} />
            ))}
          </div>
        ) : (
          <>
            {/* Hero 信号波 */}
            <div
              style={{
                position: "relative", borderRadius: 12, overflow: "hidden", border: "1px solid var(--rule)",
                background: "linear-gradient(135deg, rgba(17,29,53,0.9), rgba(7,14,26,0.95))",
                minHeight: 170, display: "flex", alignItems: "center", padding: "32px", marginBottom: 20,
              }}
            >
              <svg viewBox="0 0 1200 170" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.7, pointerEvents: "none" }}>
                <path d="M0,120 C120,80 200,140 320,100 C440,60 520,130 640,95 C760,60 840,120 960,85 C1080,50 1140,100 1200,80" fill="none" stroke="rgba(0,212,170,0.25)" strokeWidth="1" strokeDasharray="4 6" />
                <path d="M0,90 C150,60 250,110 400,80 C550,50 650,100 800,70 C950,40 1050,90 1200,60" fill="none" stroke="rgba(0,212,170,0.45)" strokeWidth="1.5" strokeDasharray="4 6" />
                <path d="M0,60 C180,35 300,80 480,55 C660,30 780,75 960,48 C1080,30 1150,55 1200,42" fill="none" stroke="#00d4aa" strokeWidth="2" />
              </svg>
              <div style={{ position: "relative", zIndex: 2, maxWidth: 560 }}>
                <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent)", marginBottom: 8 }}>
                  OMNIALPHA · AI ALPHA ENGINE
                </div>
                <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.3 }}>
                  你睡觉时，<span style={{ color: "var(--accent)" }}>AI</span> 仍在为你捕获 Alpha
                </div>
                <div style={{ color: "var(--muted)", fontSize: 14, marginTop: 8 }}>
                  AI 引擎 7×24 扫描全市场信号，智能识别、自动执行、秒级跟单——不盯盘、不错过、资金始终在你自己账户
                </div>
                <div style={{ display: "flex", gap: 24, marginTop: 20, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>接入信号源</div>
                    <div style={{ fontSize: 22, fontWeight: 700 }}>5+ 持续扩展</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>运行机器人</div>
                    <div style={{ fontSize: 22, fontWeight: 700 }}>{data.metrics.running_bots} 个</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>未实现盈亏</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: totalPnl >= 0 ? "var(--success)" : "var(--danger)" }}>
                      {totalPnl >= 0 ? "+" : ""}{fmt(totalPnl)}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 4 指标卡 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, marginBottom: 20 }}>
              {/* 可提现余额（G22 眼睛） */}
              <div className="card" style={{ position: "relative", overflow: "hidden", padding: 18 }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg, var(--accent), transparent 70%)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>可提现余额</span>
                  <span style={{ width: 26, height: 26, borderRadius: 6, display: "grid", placeItems: "center", fontSize: 12, background: "rgba(0,212,170,0.1)", color: "var(--accent)" }}>◎</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={masked ? { filter: "blur(6px)", userSelect: "none" } : undefined}>{fmt(data.metrics.available_usdt)}</span>
                  <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400 }}>USDT</span>
                  <button
                    onClick={() => setMasked((m) => !m)}
                    title={masked ? "显示金额" : "隐藏金额"}
                    style={{ background: "none", border: "none", color: "var(--tertiary)", cursor: "pointer", padding: 2, fontSize: 13 }}
                  >
                    {masked ? "🙈" : "👁"}
                  </button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12 }}>
                  <span style={{ color: "var(--success)", fontFamily: "var(--font-geist-mono)", fontWeight: 500 }}>+{fmt(data.metrics.total_reward_usdt)}</span>
                  <span style={{ color: "var(--muted)" }}>累计奖励</span>
                </div>
              </div>

              {/* 累计奖励 */}
              <div className="card" style={{ position: "relative", overflow: "hidden", padding: 18 }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg, var(--success), transparent 70%)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>累计奖励</span>
                  <span style={{ width: 26, height: 26, borderRadius: 6, display: "grid", placeItems: "center", fontSize: 12, background: "rgba(40,196,100,0.1)", color: "var(--success)" }}>⇄</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, display: "flex", alignItems: "baseline", gap: 6 }}>
                  {fmt(data.metrics.total_reward_usdt)}
                  <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400 }}>USDT</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12 }}>
                  <Link href="/rewards" style={{ color: "var(--accent)", textDecoration: "none" }}>查看明细 →</Link>
                </div>
              </div>

              {/* 运行中机器人 */}
              <div className="card" style={{ position: "relative", overflow: "hidden", padding: 18 }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg, #3b82f6, transparent 70%)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>运行中机器人</span>
                  <span style={{ width: 26, height: 26, borderRadius: 6, display: "grid", placeItems: "center", fontSize: 12, background: "rgba(59,130,246,0.1)", color: "#60a5fa" }}>▣</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, display: "flex", alignItems: "baseline", gap: 6 }}>
                  {data.metrics.running_bots}
                  <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400 }}>/ {data.metrics.total_bots} 个</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12 }}>
                  <Link href="/bots" style={{ color: "var(--accent)", textDecoration: "none" }}>管理跟单 →</Link>
                </div>
              </div>

              {/* 订阅有效期 */}
              <div className="card" style={{ position: "relative", overflow: "hidden", padding: 18 }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg, var(--warning), transparent 70%)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>订阅有效期</span>
                  <span style={{ width: 26, height: 26, borderRadius: 6, display: "grid", placeItems: "center", fontSize: 12, background: "rgba(234,179,8,0.1)", color: "var(--warning)" }}>◈</span>
                </div>
                {data.metrics.subscription.active ? (
                  <>
                    <div style={{ fontSize: 26, fontWeight: 700, display: "flex", alignItems: "baseline", gap: 6 }}>
                      {data.metrics.subscription.days_left}
                      <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400 }}>天</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
                      {data.metrics.subscription.plan_id === "monthly_19_9u" ? "正式版" : "试用版"} · 至 {data.metrics.subscription.expires_at?.slice(0, 10)}
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: 26, fontWeight: 700, color: "var(--warning)" }}>未开通</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12 }}>
                      <Link href="/subscriptions" style={{ color: "var(--accent)", textDecoration: "none" }}>立即订阅 →</Link>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* 新手引导（G23：has_api + has_bot 时隐藏） */}
            {showOnboard && (
              <div
                style={{
                  border: "1px solid rgba(0,212,170,0.35)", borderRadius: 12, padding: 24, marginBottom: 20,
                  background: "linear-gradient(135deg, rgba(0,212,170,0.07), rgba(17,29,53,0.5))",
                  display: "flex", alignItems: "center", gap: 20, position: "relative", overflow: "hidden",
                }}
              >
                <div style={{ display: "flex", gap: 16, flex: 1, flexWrap: "wrap" }}>
                  {[
                    { num: onboarding.has_api ? "✓" : "1", title: "连接账户", desc: onboarding.has_api ? "已完成 API 连接" : "1 分钟完成 API 连接，随时可撤销", done: onboarding.has_api, current: !onboarding.has_api },
                    { num: onboarding.has_bot ? "✓" : "2", title: "选择策略", desc: onboarding.has_bot ? "已选择策略" : "从策略广场挑选适合的策略", done: onboarding.has_bot, current: !onboarding.has_bot && onboarding.has_api },
                    { num: "3", title: "开启跟单", desc: "配置方向/杠杆/比例，Alpha 自动执行", done: false, current: onboarding.has_bot },
                  ].map((s, i) => (
                    <div key={i} style={{ flex: 1, minWidth: 160, display: "flex", flexDirection: "column", gap: 6 }}>
                      <span
                        style={{
                          width: 28, height: 28, borderRadius: 6, display: "grid", placeItems: "center",
                          fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600,
                          background: s.done ? "rgba(0,212,170,0.15)" : s.current ? "var(--accent)" : "transparent",
                          border: s.done ? "1px solid var(--accent)" : s.current ? "1px solid var(--accent)" : "1px solid var(--rule)",
                          color: s.done ? "var(--accent)" : s.current ? "#06281f" : "var(--muted)",
                        }}
                      >
                        {s.num}
                      </span>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{s.title}</div>
                      <div style={{ fontSize: 12, color: "var(--muted)" }}>{s.desc}</div>
                    </div>
                  ))}
                </div>
                <Link href="/strategies" className="btn btn-primary" style={{ height: 44, padding: "0 24px", whiteSpace: "nowrap" }}>
                  {onboarding.has_api ? "立即选策略" : "去绑定交易所"}
                </Link>
              </div>
            )}

            {/* 我的跟单 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h2 style={{ fontSize: 17, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />
                我的跟单机器人
              </h2>
              <Link href="/bots" style={{ color: "var(--muted)", fontSize: 12, textDecoration: "none" }}>查看全部 →</Link>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14, marginBottom: 20 }}>
              {data.bots.map((bot) => (
                <div key={bot.id} className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 15 }}>
                      {bot.strategy_name}
                      {bot.paper && (
                        <span style={{ fontSize: 11, color: "var(--accent)", background: "var(--accent-soft)", padding: "2px 8px", borderRadius: 12, marginLeft: 8, verticalAlign: "middle" }}>模拟盘</span>
                      )}
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: bot.status === "active" ? "var(--success)" : "var(--warning)", boxShadow: bot.status === "active" ? "0 0 8px var(--success)" : "none" }} />
                      {bot.status === "active" ? "运行中" : bot.status === "paused" ? "已暂停" : "已停止"}
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px", fontSize: 13 }}>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>杠杆</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600 }}>{bot.leverage}×</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>保证金模式</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600 }}>{bot.margin_mode === "isolated" ? "逐仓" : "全仓"}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>跟单比例</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600 }}>{bot.amount_mode === "fixed" ? `${bot.fixed_amount_usdt} USDT` : `${bot.percent}%`}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>持仓数</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600 }}>{bot.pnl.open_positions}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>名义价值</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600 }}>{fmt(bot.pnl.total_notional_usdt)} USDT</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>未实现盈亏</div>
                      <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 14, fontWeight: 600, color: bot.pnl.unrealized_pnl_usdt >= 0 ? "var(--success)" : "var(--danger)" }}>
                        {bot.pnl.unrealized_pnl_usdt >= 0 ? "+" : ""}{fmt(bot.pnl.unrealized_pnl_usdt)}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid var(--rule)" }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>
                      已用保证金 <strong style={{ color: "var(--fg)", fontFamily: "var(--font-geist-mono)" }}>{fmt(bot.virtual_locked_usdt)}</strong> USDT
                    </span>
                    <Link href={`/strategies/${bot.strategy_id}`} className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }}>详情</Link>
                  </div>
                </div>
              ))}
              {/* 开启新跟单 */}
              <Link
                href="/strategies"
                style={{
                  border: "1px dashed var(--rule)", borderRadius: 12, minHeight: 180, display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center", gap: 10, textDecoration: "none", color: "var(--muted)",
                }}
              >
                <div style={{ width: 48, height: 48, borderRadius: "50%", border: "1px dashed var(--tertiary)", display: "grid", placeItems: "center", fontSize: 20 }}>＋</div>
                <div style={{ fontSize: 12 }}>开启新跟单</div>
                <span className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12 }}>去策略广场</span>
              </Link>
            </div>

            {/* 双栏：实时行情（行情拉取失败时隐藏，不展示占位/假数据）+ 最近订单 */}
            <div style={{ display: "grid", gridTemplateColumns: data.tickers.length > 0 ? "1.4fr 1fr" : "1fr", gap: 16 }}>
              {data.tickers.length > 0 && (
                <div className="card" style={{ padding: 18 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h2 style={{ fontSize: 16, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />
                      实时行情
                    </h2>
                    <span style={{ fontSize: 10, color: "var(--tertiary)", fontFamily: "var(--font-geist-mono)" }}>GATE · 10s</span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 0 }}>
                    {data.tickers.map((t) => (
                      <div key={t.symbol} style={{ padding: "12px 14px", borderRight: "1px solid var(--rule)", borderBottom: "1px solid var(--rule)" }}>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, color: "var(--muted)" }}>{t.symbol}</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 15, fontWeight: 600, marginTop: 4 }}>{fmt(t.price, t.price < 1 ? 4 : 1)}</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 500, color: t.change_pct >= 0 ? "var(--success)" : "var(--danger)" }}>
                          {t.change_pct >= 0 ? "+" : ""}{t.change_pct}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="card" style={{ padding: 18 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h2 style={{ fontSize: 16, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />
                    最近跟单订单
                  </h2>
                  <Link href="/bots" style={{ color: "var(--muted)", fontSize: 12, textDecoration: "none" }}>全部 →</Link>
                </div>
                {data.recent_orders.length === 0 ? (
                  <div style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", padding: 24 }}>暂无跟单订单</div>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr>
                        {["策略", "动作", "状态"].map((h) => (
                          <th key={h} style={{ textAlign: "left", fontWeight: 600, color: "var(--muted)", padding: "8px 10px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_orders.slice(0, 6).map((o) => (
                        <tr key={o.id}>
                          <td style={{ padding: "8px 10px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" }}>{o.strategy_name ?? "—"}</td>
                          <td style={{ padding: "8px 10px", borderBottom: "1px solid var(--rule)", color: ACTION_COLOR[o.action] ?? "var(--fg)", whiteSpace: "nowrap" }}>
                            {ACTION_LABEL[o.action] ?? o.action}
                          </td>
                          <td style={{ padding: "8px 10px", borderBottom: "1px solid var(--rule)", whiteSpace: "nowrap" }}>
                            {o.status === "filled" ? (
                              <span style={{ color: "var(--success)" }}>已成交{o.latency_ms != null ? ` (${o.latency_ms}ms)` : ""}</span>
                            ) : (
                              <span style={{ color: "var(--danger)" }}>失败: {o.failure_category ?? "?"}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Toast 栈 */}
      <div style={{ position: "fixed", top: 72, right: 20, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8 }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            style={{
              minWidth: 280, maxWidth: 360, padding: "12px 16px", borderRadius: 8,
              background: "var(--surface-overlay)", border: `1px solid ${t.type === "success" ? "rgba(40,196,100,0.4)" : t.type === "error" ? "rgba(239,68,68,0.4)" : "var(--rule)"}`,
              boxShadow: "0 8px 24px rgba(0,0,0,0.35)", display: "flex", alignItems: "center", gap: 10, fontSize: 12,
            }}
          >
            <span style={{ color: t.type === "success" ? "var(--success)" : t.type === "error" ? "var(--danger)" : "var(--warning)" }}>
              {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "i"}
            </span>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </main>
  );
}
