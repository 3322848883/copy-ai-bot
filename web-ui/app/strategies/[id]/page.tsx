"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Detail = {
  id: number;
  exchange?: string;
  display_name: string;
  style: string;
  risk_rating: string;
  status: string;
  roi_7d: number;
  roi_30d: number;
  roi_90d: number;
  roi_all: number;
  win_rate_all: number;
  max_drawdown: number;
  trading_days: number;
  followers: number;
  profile_state: { is_stale: boolean; placeholder: boolean };
  positions: Position[];
  recent_orders: Order[];
};

type Position = {
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  notional_usdt?: number;
  leverage?: number;
  margin_usdt?: number;
};

type Order = {
  id: number;
  action: string;
  qty: number;
  status: string;
  executed_at?: string | null;
  symbol?: string | null;
  side?: string | null;
  price?: number | null;
  pnl?: number | null;
};

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };
const STYLE_TAG: Record<string, string> = { trend: "tag-trend", range: "tag-range", momentum: "tag-momentum" };
const RISK_SHORT: Record<string, string> = { low: "低", mid: "中", high: "高" };
const RISK_COLOR: Record<string, string> = { low: "#28c464", mid: "#eab308", high: "#ef4444" };

const ACTION_TAG: Record<string, { cls: string; label: string }> = {
  open: { cls: "act-open", label: "开仓" },
  add: { cls: "act-add", label: "加仓" },
  reduce: { cls: "act-reduce", label: "减仓" },
  close: { cls: "act-close", label: "平仓" },
};

const RATIO_OPTIONS: Array<{ label: string; mode: "fixed" | "percent"; value: number | null }> = [
  { label: "固定金额", mode: "fixed", value: null },
  { label: "比例 10%", mode: "percent", value: 10 },
  { label: "比例 20%", mode: "percent", value: 20 },
  { label: "比例 30%", mode: "percent", value: 30 },
  { label: "比例 50%", mode: "percent", value: 50 },
];

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function fmtNum(n: number, digits = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtPrice(n?: number | null) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

function fmtTime(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (x: number) => String(x).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

type EquityPoint = { date: string; value: number };
type EquityData = { points: EquityPoint[]; ranges: Record<string, EquityPoint[]>; total_points: number };

const RANGE_TABS: Array<[string, string]> = [
  ["7d", "7 天"],
  ["30d", "30 天"],
  ["90d", "90 天"],
  ["all", "历史"],
];

/** 收益曲线图（SVG 折线 + 渐变填充 + 时间范围 Tab，对齐设计稿 tab-btn 胶囊）。 */
function EquityChart({ data }: { data: EquityData }) {
  const [range, setRange] = useState("30d");
  const pts = data.ranges[range] ?? [];
  const W = 800;
  const H = 240;
  const PAD = { l: 46, r: 14, t: 18, b: 28 };

  if (pts.length < 2) {
    return <div style={{ color: "var(--muted)", fontSize: 13, padding: "24px 0" }}>暂无收益数据</div>;
  }

  const values = pts.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1e-6);
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (i / (pts.length - 1)) * innerW;
  const y = (v: number) => PAD.t + innerH - ((v - min) / span) * innerH;
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const area = `${path} L${x(pts.length - 1).toFixed(1)},${(PAD.t + innerH).toFixed(1)} L${x(0).toFixed(1)},${(PAD.t + innerH).toFixed(1)} Z`;
  const last = pts[pts.length - 1];
  const positive = last.value >= 0;
  const color = positive ? "#28c464" : "#ef4444";
  const gid = `eq-grad-${range}`;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {RANGE_TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setRange(key)}
            style={{
              padding: "6px 16px", borderRadius: 999, fontSize: 12, cursor: "pointer",
              border: range === key ? "1px solid var(--accent)" : "1px solid var(--rule)",
              background: range === key ? "var(--accent-soft)" : "transparent",
              color: range === key ? "var(--accent)" : "var(--muted)",
              fontWeight: range === key ? 500 : 400,
              fontFamily: "inherit",
            }}
          >
            {label}
          </button>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", alignSelf: "center" }}>
          区间收益 <strong style={{ color, fontSize: 15 }}>{last.value >= 0 ? "+" : ""}{last.value.toFixed(1)}%</strong>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={positive ? "#28c464" : "#ef4444"} stopOpacity="0.32" />
            <stop offset="100%" stopColor={positive ? "#28c464" : "#ef4444"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const gy = PAD.t + innerH * t;
          return <line key={t} x1={PAD.l} x2={W - PAD.r} y1={gy} y2={gy} stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 4" />;
        })}
        <path d={area} fill={`url(#${gid})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" filter="drop-shadow(0 0 8px rgba(0,212,170,0.35))" />
        {pts.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r="2.2" fill={color} />
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const v = min + span * (1 - t);
          return (
            <text key={t} x={PAD.l - 8} y={PAD.t + innerH * t + 4} textAnchor="end" fontSize="10" fill="var(--muted)">
              {v >= 0 ? "+" : ""}{v.toFixed(0)}%
            </text>
          );
        })}
        <text x={x(0)} y={H - 8} fontSize="10" fill="var(--muted)">{pts[0].date.slice(5)}</text>
        <text x={x(pts.length - 1)} y={H - 8} textAnchor="end" fontSize="10" fill="var(--muted)">{last.date.slice(5)}</text>
      </svg>
    </div>
  );
}

/** M2 T2.10 策略详情（对齐设计稿）：面包屑 + hero 大卡（5 项大数字 meta + 大按钮 + 已绑定交易所）+
 *  持仓卡片化 pos-card + 交易表 7 列（action-tag 四色）+ 交易记录分页 + 跟单弹窗高级字段。
 *  保留现有 /v1/strategies/{id} 与 /equity API、风控确认与一键跟单逻辑。 */
export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [equity, setEquity] = useState<EquityData | null>(null);
  const [err, setErr] = useState("");
  // 交易记录分页
  const [orderPage, setOrderPage] = useState(1);
  const ORDER_PAGE_SIZE = 10;
  // ★ 一键跟单（高级字段：方向跟随/保证金模式/跟单比例/单笔最大名义价值）
  const [followOpen, setFollowOpen] = useState(false);
  const [form, setForm] = useState({
    leverage: 10,
    margin_mode: "isolated",
    ratio: "比例 20%",
    maxNotional: 10000,
    paper: false,
  });
  const [formMsg, setFormMsg] = useState("");

  useEffect(() => {
    apiFetch<Detail>(`/v1/strategies/${params.id}`)
      .then(setDetail)
      .catch((e) => setErr(e instanceof Error ? e.message : "加载失败"));
    apiFetch<EquityData>(`/v1/strategies/${params.id}/equity`)
      .then(setEquity)
      .catch(() => setEquity(null));
  }, [params.id]);

  const orders = detail?.recent_orders ?? [];
  const totalOrderPages = Math.max(1, Math.ceil(orders.length / ORDER_PAGE_SIZE));
  const pageOrders = orders.slice((orderPage - 1) * ORDER_PAGE_SIZE, orderPage * ORDER_PAGE_SIZE);

  async function createBot() {
    if (!detail) return;
    setFormMsg("");
    try {
      if (!tokenStore.access) {
        router.push("/login");
        return;
      }
      // ★ M4 修复（合规）：首次跟单强制确认风险揭示（后端 create_bot 亦强制校验）
      if (!tokenStore.riskAccepted) {
        if (!window.confirm("跟单交易具有高风险，可能导致全部本金损失。\n阅读并同意《服务条款》与《风险揭示》后，确认继续？")) {
          return;
        }
        try {
          await apiFetch("/v1/auth/accept-risk-disclosure", { method: "POST" }, tokenStore.access);
          tokenStore.setRiskAccepted(true);
        } catch {
          setFormMsg("风险揭示确认失败，请稍后再试");
          return;
        }
      }
      const keys = await apiFetch<{ items: Array<{ exchange: string; id: number }> }>("/v1/apikeys", {}, tokenStore.access);
      // 跨所跟单：绑定任意交易所 API 即可跟单任意信号源，优选 Gate
      const bound = keys.items ?? [];
      const key = bound.find((k) => k.exchange === "gate") ?? bound[0];
      if (!key) {
        setFormMsg("请先到「我的账户」绑定任一交易所 API Key 后再开启跟单");
        return;
      }
      const ratio = RATIO_OPTIONS.find((o) => o.label === form.ratio) ?? RATIO_OPTIONS[2];
      await apiFetch(
        "/v1/bots",
        {
          method: "POST",
          body: JSON.stringify({
            strategy_id: detail.id, exchange: key.exchange, api_key_id: key.id,
            amount_mode: ratio.mode,
            percent: ratio.mode === "percent" ? ratio.value : null,
            fixed_amount_usdt: ratio.mode === "fixed" ? 500 : null,
            leverage: form.leverage,
            margin_mode: form.margin_mode,
            max_total_position_usdt: form.maxNotional,
            paper: form.paper,
          }),
        },
        tokenStore.access
      );
      setFormMsg("跟单机器人已创建");
      setTimeout(() => { setFollowOpen(false); router.push("/bots"); }, 900);
    } catch (e) {
      setFormMsg(e instanceof Error ? e.message : "创建失败");
    }
  }

  if (err) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", position: "relative" }}>
        <div className="aurora" />
        <div className="error-box">{err}</div>
      </main>
    );
  }
  if (!detail) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", position: "relative" }}>
        <div className="aurora" />
        <div style={{ color: "var(--muted)" }}>加载中…</div>
      </main>
    );
  }

  const listed = detail.status === "listed";
  const desc =
    `${STYLE_LABEL[detail.style] ?? detail.style}策略，全市场信号实时跟随、自动执行。` +
    `已运行 ${detail.trading_days} 天，累计胜率 ${detail.win_rate_all.toFixed(1)}%，` +
    `历史最大回撤 ${detail.max_drawdown.toFixed(1)}%，开平仓秒级同步。`;

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <style>{`
        .saas-poscard { transition: border-color .15s; }
        .saas-poscard:hover { border-color: rgba(0,212,170,.35); }
      `}</style>

      <div className="page-wrap">
        {/* 面包屑 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--muted)", marginBottom: 16 }}>
          <Link href="/strategies" style={{ color: "var(--muted)", textDecoration: "none" }}>策略广场</Link>
          <span style={{ color: "var(--tertiary)", fontFamily: "var(--font-geist-mono)" }}>/</span>
          <span style={{ color: "var(--fg)", fontWeight: 500 }}>{detail.display_name}</span>
        </div>

        {/* ★ T2.11 缓存兜底标注 */}
        {detail.profile_state?.placeholder && (
          <div style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.35)", color: "#fbbf24", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 12 }}>
            数据同步中，请稍后查看
          </div>
        )}
        {detail.profile_state?.is_stale && (
          <div style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.35)", color: "#fbbf24", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 12 }}>
            数据更新于昨日（画像同步延迟）· 最新信号仍实时推送，收益率曲线暂缓更新
          </div>
        )}

        {/* hero 大卡：名称 + 风格标签 + 运行中 badge + 描述 + 5 项大数字 meta + 右侧大按钮 + 已绑定交易所 */}
        <div
          style={{
            position: "relative", overflow: "hidden", background: "var(--surface)", border: "1px solid var(--rule)",
            borderRadius: 10, padding: 28, display: "flex", justifyContent: "space-between", alignItems: "center",
            gap: 24, flexWrap: "wrap", marginBottom: 16,
          }}
        >
          <div style={{ position: "absolute", bottom: -60, right: -60, width: 240, height: 240, borderRadius: "50%", background: "radial-gradient(circle, rgba(0,212,170,0.1), transparent 70%)", pointerEvents: "none" }} />
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 12, flex: 1, minWidth: 320 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <span style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em" }}>{detail.display_name}</span>
              <span className={`tag ${STYLE_TAG[detail.style] ?? ""}`} style={{ fontSize: 11, padding: "3px 12px" }}>{STYLE_LABEL[detail.style] ?? detail.style}</span>
              {listed ? (
                <span className="badge badge-ok">运行中</span>
              ) : (
                <span className={`badge ${detail.status === "paused" ? "badge-warn" : "badge-muted"}`}>
                  {detail.status === "paused" ? "已暂停" : "已下架"}
                </span>
              )}
            </div>
            <div style={{ color: "var(--muted)", maxWidth: 620 }}>{desc}</div>
            <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginTop: 4 }}>
              {[
                { label: "30日收益", value: `${detail.roi_30d >= 0 ? "+" : ""}${detail.roi_30d.toFixed(1)}%`, color: detail.roi_30d >= 0 ? "var(--success)" : "var(--danger)", big: true },
                { label: "累计胜率", value: `${detail.win_rate_all.toFixed(1)}%`, color: undefined, big: true },
                { label: "风险评级", value: RISK_SHORT[detail.risk_rating] ?? detail.risk_rating, color: RISK_COLOR[detail.risk_rating], big: false },
                { label: "跟单人数", value: fmt(detail.followers), color: undefined, big: false },
                { label: "最大回撤", value: `-${detail.max_drawdown.toFixed(1)}%`, color: "var(--warning)", big: false },
              ].map((m) => (
                <div key={m.label}>
                  <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{m.label}</div>
                  <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: m.big ? 22 : 16, fontWeight: 700, color: m.color ?? "var(--fg)", marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
                    {m.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 12, alignItems: "stretch" }}>
            {listed ? (
              <button className="btn btn-primary" style={{ height: 48, padding: "0 32px", fontSize: 16, fontWeight: 600 }} onClick={() => setFollowOpen(true)}>
                开启跟单
              </button>
            ) : (
              <button className="btn btn-secondary" style={{ height: 48, padding: "0 32px", fontSize: 16, opacity: 0.5, cursor: "not-allowed" }} disabled>
                已停止跟单
              </button>
            )}
            <span style={{ fontSize: 10, color: "var(--tertiary)", textAlign: "center" }}>
              信号源由平台审核上架 · 每笔跟单均实时执行风控检查
            </span>
          </div>
        </div>

        {/* 收益曲线 */}
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot" />收益曲线</div>
            <span className="panel-sub">EQUITY · 每日画像快照</span>
          </div>
          {equity ? (
            <EquityChart data={equity} />
          ) : (
            <div style={{ color: "var(--muted)", fontSize: 13, padding: "24px 0" }}>收益数据加载中…</div>
          )}
        </div>

        {/* 实时持仓（pos-card 卡片化） */}
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-hdr">
            <div className="panel-title">
              <span className="sec-dot" />实时持仓
              <span className="badge badge-muted" style={{ fontSize: 10 }}>{detail.positions.length}</span>
            </div>
            <span className="panel-sub">WS · bot.position 实时推送</span>
          </div>
          {detail.positions.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13, padding: "16px 0" }}>数据同步中，请稍后查看</div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
              {detail.positions.map((p, i) => (
                <div key={i} className="saas-poscard" style={{ border: "1px solid var(--rule)", borderRadius: 10, padding: 16, background: "var(--bg)", display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--font-geist-mono)", fontWeight: 600 }}>{p.symbol}</span>
                    <span
                      style={{
                        fontFamily: "var(--font-geist-mono)", fontSize: 11, fontWeight: 600, padding: "1px 8px", borderRadius: 4,
                        color: p.side === "long" ? "var(--success)" : "var(--danger)",
                        background: p.side === "long" ? "rgba(40,196,100,0.12)" : "rgba(239,68,68,0.12)",
                      }}
                    >
                      {p.side === "long" ? "做多" : "做空"}
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 12px" }}>
                    {[
                      ["数量", `${p.qty}`],
                      ["杠杆", p.leverage != null ? `${p.leverage}×` : "—"],
                      ["开仓价", fmtPrice(p.entry_price)],
                      ["标记价", fmtPrice(p.mark_price)],
                      ["名义价值", p.notional_usdt != null ? `${fmtNum(p.notional_usdt)} USDT` : "—"],
                      ["保证金", p.margin_usdt != null ? `${fmtNum(p.margin_usdt)} USDT` : "—"],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{k}</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 12, fontWeight: 600, marginTop: 2 }}>{v}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 10, borderTop: "1px solid rgba(51,65,85,0.4)" }}>
                    <span style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>未实现盈亏</span>
                    <span style={{ fontFamily: "var(--font-geist-mono)", fontWeight: 600, color: p.unrealized_pnl >= 0 ? "var(--success)" : "var(--danger)" }}>
                      {p.unrealized_pnl >= 0 ? "+" : ""}{fmtNum(p.unrealized_pnl)} USDT
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 最近交易记录（7 列 + action-tag 四色 + 分页） */}
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title">
              <span className="sec-dot" />最近交易记录
              <span className="badge badge-muted" style={{ fontSize: 10 }}>{orders.length}</span>
            </div>
            <span className="panel-sub">动作含开仓/加仓/减仓/平仓</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="ftx-table" style={{ minWidth: 760 }}>
              <thead>
                <tr>
                  <th>时间</th><th>币对</th><th>动作</th><th>方向</th>
                  <th className="num">数量</th><th className="num">价格</th><th className="num">盈亏</th>
                </tr>
              </thead>
              <tbody>
                {pageOrders.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: "center", color: "var(--muted)", padding: "28px 0" }}>数据同步中，请稍后查看</td>
                  </tr>
                ) : (
                  pageOrders.map((o) => {
                    const act = ACTION_TAG[o.action];
                    return (
                      <tr key={o.id}>
                        <td className="num">{fmtTime(o.executed_at)}</td>
                        <td>{o.symbol ?? "—"}</td>
                        <td>
                          <span className={`action-tag ${act?.cls ?? ""}`}>{act?.label ?? o.action}</span>
                        </td>
                        <td style={{ color: o.side === "long" ? "var(--success)" : o.side === "short" ? "var(--danger)" : "var(--muted)" }}>
                          {o.side === "long" ? "多" : o.side === "short" ? "空" : "—"}
                        </td>
                        <td className="num">{o.qty}</td>
                        <td className="num">{fmtPrice(o.price)}</td>
                        <td className="num" style={{ color: o.pnl == null ? "var(--muted)" : o.pnl >= 0 ? "var(--success)" : "var(--danger)" }}>
                          {o.pnl == null ? "—" : `${o.pnl >= 0 ? "+" : ""}${fmtNum(o.pnl)}`}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {orders.length > ORDER_PAGE_SIZE && (
            <div className="pagination" style={{ justifyContent: "center", marginTop: 16 }}>
              <button className="page-btn" disabled={orderPage <= 1} onClick={() => setOrderPage(orderPage - 1)}>‹</button>
              {Array.from({ length: totalOrderPages }, (_, i) => i + 1).map((n) => (
                <button key={n} className={`page-btn ${n === orderPage ? "active" : ""}`} onClick={() => setOrderPage(n)}>{n}</button>
              ))}
              <button className="page-btn" disabled={orderPage >= totalOrderPages} onClick={() => setOrderPage(orderPage + 1)}>›</button>
            </div>
          )}
        </div>
      </div>

      {/* ★ 跟单弹窗（高级字段：方向跟随/仅多/仅空、保证金模式逐仓/全仓、跟单比例固定金额/比例、单笔最大名义价值、风控预检） */}
      {followOpen && detail && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", backdropFilter: "blur(4px)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) { setFollowOpen(false); setFormMsg(""); } }}
        >
          <div style={{ width: 520, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>开启跟单</div>
              <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => { setFollowOpen(false); setFormMsg(""); }}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {detail.display_name} · <span className={`tag ${STYLE_TAG[detail.style] ?? ""}`}>{STYLE_LABEL[detail.style] ?? detail.style}</span>
              <span className="badge badge-ok">运行中</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="label">杠杆倍数</label>
                <select className="input" value={form.leverage} onChange={(e) => setForm({ ...form, leverage: Number(e.target.value) })}>
                  {[10, 5, 3, 1].map((lv) => <option key={lv} value={lv}>{lv}×</option>)}
                </select>
              </div>
              <div>
                <label className="label">保证金模式</label>
                <select className="input" value={form.margin_mode} onChange={(e) => setForm({ ...form, margin_mode: e.target.value })}>
                  <option value="isolated">逐仓</option>
                  <option value="cross">全仓</option>
                </select>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="label">跟单比例</label>
                <select className="input" value={form.ratio} onChange={(e) => setForm({ ...form, ratio: e.target.value })}>
                  {RATIO_OPTIONS.map((o) => <option key={o.label} value={o.label}>{o.label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">单笔最大名义价值</label>
                <input
                  className="input"
                  type="number" min={1}
                  value={form.maxNotional}
                  onChange={(e) => setForm({ ...form, maxNotional: Number(e.target.value) })}
                  placeholder="例：500 USDT（留空用比例）"
                />
              </div>
            </div>
            <label className="label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 0 }}>
              <input type="checkbox" checked={form.paper} onChange={(e) => setForm({ ...form, paper: e.target.checked })} />
              模拟盘（沙箱验证，不触达真实资金）
            </label>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 6, background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: 12, color: "var(--warning)" }}>
              <span>⚠</span>
              <span>本策略为高风险合约交易，历史最大回撤 {detail.max_drawdown.toFixed(1)}%。我已阅读并同意<Link href="/terms" style={{ color: "var(--warning)" }}>风险揭示</Link>。</span>
            </div>
            {formMsg && (
              <div style={{ color: formMsg.includes("已创建") ? "var(--success)" : "var(--danger)", fontSize: 13 }}>{formMsg}</div>
            )}
            <button className="btn btn-primary" style={{ height: 48, fontSize: 15, fontWeight: 600, width: "100%" }} onClick={createBot}>
              确认开启跟单
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
