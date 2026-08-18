"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { ToastStack, useToasts } from "@/components/Toast";
import { usePlatformConfig, type PlatformConfig } from "@/lib/config";

type InviteItem = { invitee_email: string; bound_at: string; reward_usdt: number; reward_status: string; verifying_ends_at: string | null };
type Risk = { risk_flag: boolean };
type Stats = { total_invitees: number; total_reward: number; verifying_reward: number; frozen_reward: number; available_reward: number; withdrawn_reward: number };

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  verifying: { label: "核实中", cls: "badge-warn" },
  available: { label: "可提现", cls: "badge-ok" },
  withdrawing: { label: "提现中", cls: "badge-info" },
  paid: { label: "已发放", cls: "badge-ok" },
  frozen: { label: "冻结", cls: "badge-err" },
  canceled: { label: "已取消", cls: "badge-err" },
  paid_failed: { label: "发放失败", cls: "badge-err" },
  rolled_back: { label: "已回滚", cls: "badge-muted" },
  none: { label: "未产生奖励", cls: "badge-muted" },
};

const rulesOf = (cfg: PlatformConfig): Array<[string, string]> => [
  [`奖励比例 ${cfg.referral.reward_pct}%`, `好友每笔订阅费的 ${cfg.referral.reward_pct}% 计入你的奖励，无封顶`],
  [`${cfg.referral.verify_hours} 小时核实期`, `订阅成功后进入 ${cfg.referral.verify_hours}h 核实，核实期内好友退款则奖励自动取消（高危账号延长至 ${cfg.referral.abuse_verify_hours}h）`],
  ["可提现门槛", `奖励到账后可提现，最低 ${cfg.withdraw.min_withdrawal_usdt} U 起提 + ${cfg.withdraw.fee_usdt} U 手续费，支持 TRC-20 / BEP-20 / ERC-20 / APTOS`],
  ["奖励实时通知", "好友绑定、奖励到账、提现进度均通过站内消息实时推送"],
];

/** 邀请中心：奖励 Hero + 核实时间轴 + 收益趋势 + 流水账本 + 规则说明（数值全部来自 /v1/config）。 */
export default function InvitePage() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [risk, setRisk] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [posterOpen, setPosterOpen] = useState(false);
  const posterRef = useRef<HTMLCanvasElement>(null);
  // ★ 收益趋势范围 Tab + 核实倒计时
  const [range, setRange] = useState(30);
  const [now, setNow] = useState(Date.now());
  const { toasts, push: showToast, dismiss } = useToasts();
  const cfg = usePlatformConfig();
  const RULES = rulesOf(cfg);

  const shareUrl = typeof window !== "undefined" ? `${window.location.origin}/register?invite=${code}` : "";

  const load = useCallback(async () => {
    try {
      const [c, list, r, s] = await Promise.all([
        apiFetch<{ code: string }>("/v1/referrals/code", {}, tokenStore.access),
        apiFetch<{ items: InviteItem[] }>("/v1/referrals/invites", {}, tokenStore.access),
        apiFetch<Risk>("/v1/referrals/risk", {}, tokenStore.access),
        apiFetch<Stats>("/v1/referrals/stats", {}, tokenStore.access),
      ]);
      setCode(c.code);
      setInvites(list.items);
      setRisk(r.risk_flag);
      setStats(s);
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
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [load, router]);

  async function copyText(text: string, okMsg: string) {
    try {
      await navigator.clipboard.writeText(text);
      showToast("success", okMsg);
    } catch {
      showToast("warn", "复制失败，请手动复制");
    }
  }

  // ★ M6 保存海报：canvas 绘制邀请海报并下载 PNG
  function drawPoster() {
    const canvas = posterRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, "#0b1a33");
    grad.addColorStop(0.55, "#0e2440");
    grad.addColorStop(1, "#0a1428");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
    // 装饰圆环
    ctx.strokeStyle = "rgba(0,212,170,0.25)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(W - 60, 70, 110, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(50, H - 80, 80, 0, Math.PI * 2);
    ctx.stroke();
    // 标题
    ctx.fillStyle = "#00d4aa";
    ctx.font = "700 34px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("OmniAlpha · Alpha 一直在被捕获", W / 2, 110);
    ctx.fillStyle = "#f1f5f9";
    ctx.font = "500 18px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText(`好友注册即享 ${cfg.referral.reward_pct}% 返佣奖励`, W / 2, 158);
    // 邀请码框
    ctx.fillStyle = "rgba(0,212,170,0.12)";
    ctx.strokeStyle = "#00d4aa";
    ctx.lineWidth = 2;
    const boxW = 300;
    const boxH = 96;
    const bx = (W - boxW) / 2;
    const by = 200;
    ctx.beginPath();
    ctx.roundRect(bx, by, boxW, boxH, 14);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#94a3b8";
    ctx.font = "400 14px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText("我的专属邀请码", W / 2, by + 32);
    ctx.fillStyle = "#00d4aa";
    ctx.font = "800 40px monospace";
    ctx.fillText(code || "······", W / 2, by + 74);
    // 说明
    ctx.fillStyle = "#94a3b8";
    ctx.font = "400 14px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText("注册时填写邀请码，好友购买套餐后您获得奖励", W / 2, H - 90);
    ctx.fillText(`奖励核实期 ${cfg.referral.verify_hours}h · 风控场景 ${cfg.referral.abuse_verify_hours}h`, W / 2, H - 62);
  }

  useEffect(() => {
    if (posterOpen) drawPoster();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posterOpen, code, cfg]);

  function savePoster() {
    const canvas = posterRef.current;
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `邀请海报-${code}.png`;
    a.click();
    showToast("success", "海报已保存");
  }

  /* ── 统计卡直接使用后端按 Reward 状态聚合的口径（与奖励账本页一致）── */
  const frozenTotal = stats?.frozen_reward ?? 0;

  const statCards: Array<{ label: string; val: string; sub: string; color?: string }> = [
    { label: "已邀请", val: `${stats?.total_invitees ?? 0}`, sub: "人 · 好友注册绑定" },
    { label: "累计奖励", val: (stats?.total_reward ?? 0).toFixed(2), sub: "USDT · 全部邀请奖励合计", color: "var(--success)" },
    { label: "待核实", val: (stats?.verifying_reward ?? 0).toFixed(2), sub: `USDT · ${cfg.referral.verify_hours}h 核实倒计时`, color: "var(--warning)" },
    { label: "冻结奖励", val: frozenTotal.toFixed(2), sub: `USDT · ${cfg.referral.abuse_verify_hours}h 风控核实`, color: "var(--danger)" },
    { label: "已提现奖励", val: (stats?.withdrawn_reward ?? 0).toFixed(2), sub: "USDT · 提现中 + 已打款" },
  ];

  /* ── 核实时间轴（取最新一条邀请的真实状态）── */
  const latest = invites[0] || null;
  const latestStatus = latest?.reward_status || "none";
  const verifyEnd = latest?.verifying_ends_at ? new Date(latest.verifying_ends_at).getTime() : null;
  const verifyTotal = latestStatus === "frozen" ? cfg.referral.abuse_verify_hours * 3600_000 : cfg.referral.verify_hours * 3600_000;
  const verifyLeft = verifyEnd ? Math.max(0, verifyEnd - now) : 0;
  const verifyPct = verifyEnd ? Math.min(100, Math.max(0, (1 - verifyLeft / verifyTotal) * 100)) : 0;
  const cdText = verifyEnd
    ? `${Math.floor(verifyLeft / 3600_000)}h ${String(Math.floor((verifyLeft % 3600_000) / 60_000)).padStart(2, "0")}m ${String(Math.floor((verifyLeft % 60_000) / 1000)).padStart(2, "0")}s`
    : "";

  const step2Active = latestStatus === "verifying" || latestStatus === "frozen";
  const step3Done = latestStatus === "available" || latestStatus === "withdrawing" || latestStatus === "paid";

  /* ── 收益趋势（真实邀请数据分桶柱状图）── */
  const BARS = 15;
  function buildTrend(): { heights: number[]; cum: number[]; maxV: number; totalV: number } {
    const bucket = new Array(BARS).fill(0);
    const dayMs = 86400_000;
    const windowMs = range * dayMs;
    for (const inv of invites) {
      const t = new Date(inv.bound_at).getTime();
      const diff = now - t;
      if (diff < 0 || diff > windowMs) continue;
      const idx = Math.min(BARS - 1, Math.floor((diff / windowMs) * BARS));
      bucket[idx] += inv.reward_usdt;
    }
    const cum: number[] = [];
    let acc = 0;
    let maxV = 0;
    let totalV = 0;
    for (let i = 0; i < BARS; i++) {
      acc += bucket[i];
      cum.push(acc);
      maxV = Math.max(maxV, bucket[i]);
      totalV += bucket[i];
    }
    return { heights: bucket, cum, maxV, totalV };
  }
  const trend = buildTrend();
  const chartH = 120;
  const barW = 14;
  const barGap = 36;
  const barY = (v: number) => (trend.maxV > 0 ? Math.round(chartH - (v / trend.maxV) * chartH) : chartH);
  const maxCum = trend.cum[BARS - 1] || 1;
  const cumY = (i: number) => Math.round(chartH - (trend.cum[i] / maxCum) * (chartH * 0.6) - 4);
  const cumPath = trend.cum.map((_, i) => `${i === 0 ? "M" : "L"}${18 + i * barGap},${cumY(i)}`).join(" ");
  const endLabel = new Date(now - range * 86400_000).toISOString().slice(5, 10).replace("-", "-");
  const startLabel = new Date(now).toISOString().slice(5, 10);

  /* ── 流水备注 ── */
  function remark(inv: InviteItem): string {
    switch (inv.reward_status) {
      case "verifying": return `${cfg.referral.verify_hours}h 核实 · 通过后自动入账`;
      case "frozen": return `批量邀请风控 · ${cfg.referral.abuse_verify_hours}h 核实`;
      case "available": return "核实通过 · 已计入可提现余额";
      case "withdrawing": return "已发起提现 · 关联提现单";
      case "paid": return "转入提现流程 · TxHash 已记录";
      case "canceled": return "下级退款 · 奖励回滚";
      case "rolled_back": return "奖励回滚（风控）";
      case "paid_failed": return "发放失败 · 已进入异常池";
      default: return "—";
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
            <div className="page-eyebrow">REFERRAL REWARDS · 邀请奖励</div>
            <h1 className="page-title">邀请奖励<small>好友订阅 · 你拿 {cfg.referral.reward_pct}% 现金奖励</small></h1>
          </div>
        </div>

        {/* 邀请 Hero：大标题 + 奖励比例徽章 + 邀请码 code-box + 分享/海报 */}
        <div
          style={{
            position: "relative", borderRadius: 10, overflow: "hidden", border: "1px solid var(--rule)",
            background: "linear-gradient(135deg, rgba(0,212,170,0.09), rgba(17,29,53,0.6))",
            padding: 28, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24,
            marginBottom: 24, flexWrap: "wrap",
          }}
        >
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 8, minWidth: 260, flex: 1 }}>
            <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.01em" }}>邀请好友，享 {cfg.referral.reward_pct}% 现金奖励</div>
            <div style={{ color: "var(--muted)", maxWidth: 480 }}>
              好友通过你的邀请码注册并订阅，你将获得其订阅费 {cfg.referral.reward_pct}% 的现金奖励，直接进入可提现余额，无上限、无封顶。
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
              <span
                style={{
                  padding: "8px 20px", borderRadius: 6, background: "rgba(0,212,170,0.15)",
                  border: "1px solid rgba(0,212,170,0.4)", fontSize: 22, fontWeight: 700, color: "var(--accent)",
                }}
              >
                {cfg.referral.reward_pct}%
              </span>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                <strong style={{ color: "var(--fg)" }}>好友每笔订阅费</strong>
                <br />奖励核实通过后进入可提现余额
              </div>
            </div>
          </div>
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 12, minWidth: 340, flex: 1, maxWidth: 440 }}>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>我的专属邀请码</div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: 16, borderRadius: 10, background: "#070e1a", border: "1px dashed #009a7a" }}>
              <span style={{ flex: 1, textAlign: "center", fontFamily: "var(--font-geist-mono), monospace", fontSize: 20, fontWeight: 600, letterSpacing: 3, color: "var(--fg)" }}>
                {code || "······"}
              </span>
              <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 12, height: 32 }} onClick={() => copyText(code, `邀请码已复制：${code}`)}>
                复制
              </button>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => copyText(shareUrl, "分享链接已复制，去发送给好友吧")}>
                分享链接
              </button>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setPosterOpen(true)}>
                保存海报
              </button>
            </div>
          </div>
        </div>

        {/* 5 张统计卡 */}
        <div className="kpi-grid" style={{ marginBottom: 24 }}>
          {statCards.map((c) => (
            <div key={c.label} className="kpi-card">
              <div className="kpi-l">{c.label}</div>
              <div className="kpi-v" style={c.color ? { color: c.color } : undefined}>{c.val}</div>
              <div className="kpi-s">{c.sub}</div>
            </div>
          ))}
        </div>

        {/* 双栏：核实时间轴 + 收益趋势 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(430px, 1fr))", gap: 24, marginBottom: 24 }}>
          {/* 奖励核实时间轴 */}
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>奖励核实状态</div>
              <span className="panel-sub">WS · reward.tick 实时倒计时</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {/* 步骤 1：下级订阅成功 */}
              <div style={{ display: "flex", gap: 16, position: "relative", paddingBottom: 16 }}>
                <div style={{ position: "absolute", left: 11, top: 24, bottom: 0, width: 1, background: "var(--rule)" }} />
                <div style={{ width: 24, height: 24, borderRadius: "50%", border: "2px solid var(--success)", background: "rgba(22,163,74,0.15)", color: "var(--success)", display: "grid", placeItems: "center", flexShrink: 0, zIndex: 1, fontSize: 10 }}>
                  ✓
                </div>
                <div style={{ flex: 1, paddingTop: 2 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>
                    下级订阅成功 <span className="badge badge-ok">已完成</span>
                  </div>
                  <div style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, color: "var(--tertiary)", marginTop: 2 }}>
                    {latest ? latest.bound_at?.slice(0, 16) : "—"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    {latest
                      ? `${latest.invitee_email} 支付订阅 · 触发 ${cfg.referral.reward_pct}% 奖励 = ${latest.reward_usdt.toFixed(2)} U`
                      : "暂无邀请，分享邀请码给好友开始"}
                  </div>
                </div>
              </div>

              {/* 步骤 2：奖励核实中 */}
              <div style={{ display: "flex", gap: 16, position: "relative", paddingBottom: 16 }}>
                <div style={{ position: "absolute", left: 11, top: 24, bottom: 0, width: 1, background: "var(--rule)" }} />
                <div
                  style={{
                    width: 24, height: 24, borderRadius: "50%", border: step2Active ? "2px solid var(--accent)" : "2px solid var(--rule)",
                    background: step2Active ? "rgba(0,212,170,0.15)" : "var(--surface)",
                    color: step2Active ? "var(--accent)" : "var(--muted)",
                    boxShadow: step2Active ? "0 0 0 4px rgba(0,212,170,0.1)" : undefined,
                    display: "grid", placeItems: "center", flexShrink: 0, zIndex: 1, fontSize: 10,
                  }}
                >
                  {step2Active ? "◌" : step3Done ? "✓" : "◌"}
                </div>
                <div style={{ flex: 1, paddingTop: 2 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>
                    奖励核实中
                    {step2Active ? (
                      <span className="badge badge-warn">verifying</span>
                    ) : step3Done ? (
                      <span className="badge badge-ok">已完成</span>
                    ) : (
                      <span className="badge badge-muted">待开始</span>
                    )}
                  </div>
                  <div style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, color: "var(--tertiary)", marginTop: 2 }}>
                    {step2Active && verifyEnd ? `剩余 ${cdText} · ${latestStatus === "frozen" ? `${cfg.referral.abuse_verify_hours}h` : `${cfg.referral.verify_hours}h`} 倒计时` : "—"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    {latestStatus === "frozen"
                      ? `风控检测到批量邀请行为 · 已延长核实至 ${cfg.referral.abuse_verify_hours}h`
                      : "核实期内下级退款则奖励取消 · 通过后自动转入可提现余额"}
                  </div>
                  {step2Active && (
                    <div style={{ height: 6, background: "#070e1a", borderRadius: 999, overflow: "hidden", marginTop: 8 }}>
                      <div
                        style={{
                          height: "100%", borderRadius: 999, transition: "width .6s ease",
                          background: latestStatus === "frozen"
                            ? "linear-gradient(90deg, var(--warning), #facc15)"
                            : "linear-gradient(90deg, #009a7a, var(--accent))",
                          width: `${verifyPct}%`,
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* 步骤 3：奖励到账 */}
              <div style={{ display: "flex", gap: 16, position: "relative", paddingBottom: 0 }}>
                <div
                  style={{
                    width: 24, height: 24, borderRadius: "50%", border: step3Done ? "2px solid var(--success)" : "2px solid var(--rule)",
                    background: step3Done ? "rgba(22,163,74,0.15)" : "var(--surface)",
                    color: step3Done ? "var(--success)" : "var(--muted)",
                    display: "grid", placeItems: "center", flexShrink: 0, zIndex: 1, fontSize: 10,
                  }}
                >
                  ◎
                </div>
                <div style={{ flex: 1, paddingTop: 2 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 8 }}>
                    奖励到账 <span className="badge badge-muted">available</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    核实通过 → 计入可提现余额 → 可申请提现（10U 起提）
                  </div>
                </div>
              </div>
            </div>

            {/* 风控黄条（批量邀请冻结提醒） */}
            {risk && (
              <div
                style={{
                  marginTop: 16, padding: 12, borderRadius: 6, border: "1px solid rgba(234,179,8,0.3)",
                  background: "rgba(234,179,8,0.06)", fontSize: 12, color: "var(--warning)", lineHeight: 1.6,
                }}
              >
                ⚠ 检测到批量邀请行为，冻结奖励 {frozenTotal.toFixed(2)} U 已延长核实至 {cfg.referral.abuse_verify_hours}h
              </div>
            )}
          </div>

          {/* 邀请收益趋势 */}
          <div className="panel">
            <div className="panel-hdr">
              <div className="panel-title"><span className="sec-dot"></span>邀请收益趋势</div>
              <div style={{ display: "flex", gap: 8 }}>
                {[7, 30, 90].map((d) => (
                  <button key={d} className={`chip${range === d ? " active" : ""}`} style={{ height: 26, lineHeight: "13px" }} onClick={() => setRange(d)}>
                    {d} 天
                  </button>
                ))}
              </div>
            </div>
            <div style={{ height: 200, position: "relative", borderRadius: 6, overflow: "hidden", background: "#070e1a", border: "1px solid var(--rule)" }}>
              {trend.totalV > 0 ? (
                <svg viewBox="0 0 560 200" preserveAspectRatio="none" style={{ width: "100%", height: "100%", display: "block" }}>
                  {/* 网格 */}
                  <line x1="0" y1="50" x2="560" y2="50" stroke="rgba(51,65,85,0.35)" strokeWidth="1" strokeDasharray="3 5" />
                  <line x1="0" y1="100" x2="560" y2="100" stroke="rgba(51,65,85,0.35)" strokeWidth="1" strokeDasharray="3 5" />
                  <line x1="0" y1="150" x2="560" y2="150" stroke="rgba(51,65,85,0.35)" strokeWidth="1" strokeDasharray="3 5" />
                  {/* 柱状 */}
                  {trend.heights.map((v, i) => {
                    const y = barY(v);
                    const isMax = trend.maxV > 0 && v === trend.maxV;
                    return (
                      <rect
                        key={i}
                        x={18 + i * barGap}
                        y={y + 32}
                        width={barW}
                        height={Math.max(2, chartH - y)}
                        rx={2}
                        fill={isMax ? "var(--accent)" : "rgba(0,212,170,0.45)"}
                        style={isMax ? { filter: "drop-shadow(0 0 6px rgba(0,212,170,0.4))" } : undefined}
                      />
                    );
                  })}
                  {/* 累计线 */}
                  <path d={cumPath} fill="none" stroke="#40ffc5" strokeWidth="1.5" strokeDasharray="3 4" />
                </svg>
              ) : (
                <div className="empty-state" style={{ minHeight: 200, border: "none" }}>
                  <div className="es-ic">⌁</div>
                  <div style={{ fontSize: 13 }}>近 {range} 天暂无邀请收益</div>
                </div>
              )}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-geist-mono), monospace", fontSize: 10, color: "var(--tertiary)", paddingTop: 8 }}>
              <span>{endLabel}</span>
              <span>累计 {trend.totalV.toFixed(2)} U</span>
              <span>{startLabel}</span>
            </div>
          </div>
        </div>

        {/* 奖励流水明细（6 列 ftx-table） */}
        <div className="panel" style={{ marginBottom: 24 }}>
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>奖励流水明细</div>
            <span className="panel-sub">时间 / 来源 / 下级 / 金额 / 状态 / 备注</span>
          </div>
          <table className="ftx-table">
            <thead>
              <tr><th>时间</th><th>来源</th><th>下级</th><th className="num">金额</th><th>状态</th><th>备注</th></tr>
            </thead>
            <tbody>
              {invites.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div style={{ textAlign: "center", padding: "28px 0", color: "var(--muted)", fontSize: 13 }}>暂无奖励流水，邀请好友订阅后自动生成</div>
                  </td>
                </tr>
              ) : (
                invites.map((inv, i) => {
                  const st = STATUS_BADGE[inv.reward_status] || { label: inv.reward_status, cls: "badge-muted" };
                  const positive = inv.reward_status !== "canceled" && inv.reward_status !== "rolled_back";
                  return (
                    <tr key={i}>
                      <td className="num">{inv.bound_at?.slice(0, 16) || "—"}</td>
                      <td>订阅奖励</td>
                      <td>{inv.invitee_email || "—"}</td>
                      <td className="num" style={{ color: positive ? "var(--success)" : "var(--danger)" }}>
                        {positive ? "+" : "-"}{inv.reward_usdt.toFixed(2)} U
                      </td>
                      <td><span className={`badge ${st.cls}`}>{st.label}</span></td>
                      <td className="sub-ref">{remark(inv)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 奖励规则说明 4 条 */}
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>奖励规则</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {RULES.map(([title, desc], i) => (
              <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                <span style={{ width: 24, height: 24, borderRadius: 4, background: "rgba(0,212,170,0.12)", color: "var(--accent)", display: "grid", placeItems: "center", fontFamily: "var(--font-geist-mono), monospace", fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
                  {i + 1}
                </span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{title}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Toast 栈 */}
      <ToastStack toasts={toasts} onDismiss={dismiss} />

      {/* ★ M6 海报预览弹窗 */}
      {posterOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 420, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24, textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>邀请海报</div>
            <canvas ref={posterRef} width={600} height={800} style={{ width: "100%", height: "auto", borderRadius: 10, border: "1px solid var(--rule)" }} />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setPosterOpen(false)}>关闭</button>
              <button className="btn btn-primary" onClick={savePoster}>保存海报</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
