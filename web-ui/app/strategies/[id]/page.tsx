"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Detail = {
  id: number;
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
};

type Order = {
  id: number;
  action: string;
  qty: number;
  status: string;
  executed_at?: string | null;
}

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };
const RISK_LABEL: Record<string, string> = { low: "低风险", mid: "中风险", high: "高风险" };

type EquityPoint = { date: string; value: number };
type EquityData = { points: EquityPoint[]; ranges: Record<string, EquityPoint[]>; total_points: number };

const RANGE_TABS: Array<[string, string]> = [
  ["7d", "近7日"],
  ["30d", "近30日"],
  ["90d", "近90日"],
  ["all", "全部"],
];

/** 收益曲线图（SVG 折线 + 渐变填充 + 时间范围 Tab）。 */
function EquityChart({ data }: { data: EquityData }) {
  const [range, setRange] = useState("30d");
  const pts = data.ranges[range] ?? [];
  const W = 760;
  const H = 220;
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
  const color = positive ? "var(--success)" : "var(--danger)";
  const gid = `eq-grad-${range}`;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {RANGE_TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setRange(key)}
            style={{
              padding: "4px 14px", borderRadius: 16, fontSize: 12, cursor: "pointer",
              border: range === key ? "1px solid var(--accent)" : "1px solid var(--rule)",
              background: range === key ? "var(--accent-soft)" : "transparent",
              color: range === key ? "var(--accent)" : "var(--muted)",
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
            <stop offset="0%" stopColor={positive ? "#28c464" : "#ef4444"} stopOpacity="0.35" />
            <stop offset="100%" stopColor={positive ? "#28c464" : "#ef4444"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const gy = PAD.t + innerH * t;
          return <line key={t} x1={PAD.l} x2={W - PAD.r} y1={gy} y2={gy} stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 4" />;
        })}
        <path d={area} fill={`url(#${gid})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
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

/** M2 T2.10 策略详情 + T2.11 ★G21 缓存兜底（is_stale / placeholder 标注）。 */
export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [equity, setEquity] = useState<EquityData | null>(null);
  const [err, setErr] = useState("");
  // ★ 一键跟单（与策略广场一致：比例/杠杆/模拟盘）
  const [followOpen, setFollowOpen] = useState(false);
  const [form, setForm] = useState({ percent: 20, leverage: 10, paper: false });
  const [formMsg, setFormMsg] = useState("");

  useEffect(() => {
    apiFetch<Detail>(`/v1/strategies/${params.id}`)
      .then(setDetail)
      .catch((e) => setErr(e instanceof Error ? e.message : "加载失败"));
    apiFetch<EquityData>(`/v1/strategies/${params.id}/equity`)
      .then(setEquity)
      .catch(() => setEquity(null));
  }, [params.id]);

  async function createBot() {
    if (!detail) return;
    setFormMsg("");
    try {
      if (!tokenStore.access) {
        router.push("/login");
        return;
      }
      const keys = await apiFetch<{ items: Array<{ exchange: string; id: number }> }>("/v1/apikeys", {}, tokenStore.access);
      const gateKey = keys.items?.find((k) => k.exchange === "gate");
      if (!gateKey) {
        setFormMsg("请先到「我的账户」绑定 Gate API Key");
        return;
      }
      await apiFetch(
        "/v1/bots",
        {
          method: "POST",
          body: JSON.stringify({
            strategy_id: detail.id, exchange: "gate", api_key_id: gateKey.id,
            amount_mode: "percent", percent: form.percent, leverage: form.leverage,
            margin_mode: "isolated", paper: form.paper,
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

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 880, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <Link href="/strategies" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>
          ← 返回策略广场
        </Link>

        {/* ★ T2.11 缓存兜底标注 */}
        {detail.profile_state?.placeholder && (
          <div style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.35)", color: "#fbbf24", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginTop: 16 }}>
            数据同步中，请稍后查看
          </div>
        )}
        {detail.profile_state?.is_stale && (
          <div style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.35)", color: "#fbbf24", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginTop: 16 }}>
            数据更新于昨日（今日画像尚未同步）
          </div>
        )}

        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{detail.display_name}</div>
              <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 6 }}>
                {STYLE_LABEL[detail.style]} · {RISK_LABEL[detail.risk_rating]} · 交易 {detail.trading_days} 天
              </div>
            </div>
            <span
              style={{
                fontSize: 13, padding: "4px 14px", borderRadius: 20,
                background: detail.status === "listed" ? "rgba(40,196,100,.15)" : "rgba(100,116,139,.2)",
                color: detail.status === "listed" ? "var(--success)" : "var(--muted)",
              }}
            >
              {detail.status === "listed" ? "运行中" : detail.status === "paused" ? "已暂停" : "已下架"}
            </span>
            {detail.status === "listed" && (
              <button className="btn btn-primary" onClick={() => setFollowOpen(true)} style={{ padding: "8px 22px" }}>
                开始跟单
              </button>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
            {[
              ["7日收益", `${detail.roi_7d.toFixed(1)}%`, detail.roi_7d >= 0],
              ["30日收益", `${detail.roi_30d.toFixed(1)}%`, detail.roi_30d >= 0],
              ["90日收益", `${detail.roi_90d.toFixed(1)}%`, detail.roi_90d >= 0],
              ["累计收益", `${detail.roi_all.toFixed(1)}%`, detail.roi_all >= 0],
              ["胜率", `${detail.win_rate_all.toFixed(1)}%`, true],
              ["最大回撤", `${detail.max_drawdown.toFixed(1)}%`, detail.max_drawdown <= 30],
              ["跟单人数", `${detail.followers}`, true],
              ["交易天数", `${detail.trading_days}`, true],
            ].map(([label, val, good]) => (
              <div key={label as string} className="card" style={{ padding: 14 }}>
                <div style={{ color: "var(--muted)", fontSize: 12 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: good ? "var(--success)" : "var(--danger)", marginTop: 4 }}>
                  {val}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>收益曲线</div>
          {equity ? (
            <EquityChart data={equity} />
          ) : (
            <div style={{ color: "var(--muted)", fontSize: 13, padding: "24px 0" }}>收益数据加载中…</div>
          )}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>实时持仓（{detail.positions.length}）</div>
          {detail.positions.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>数据同步中，请稍后查看</div>
          ) : (
            <div className="table-wrap">
              <table style={{ minWidth: 560 }}>
                <thead>
                  <tr>
                    <th>合约</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>名义价值</th><th>未实现盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.positions.map((p, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                      <td style={{ color: p.side === "long" ? "var(--success)" : "var(--danger)" }}>{p.side === "long" ? "多" : "空"}</td>
                      <td>{p.qty}</td>
                      <td>{p.entry_price}</td>
                      <td>{p.mark_price}</td>
                      <td>{p.notional_usdt != null ? `${p.notional_usdt.toFixed(2)} USDT` : "—"}</td>
                      <td style={{ color: p.unrealized_pnl >= 0 ? "var(--success)" : "var(--danger)" }}>{p.unrealized_pnl.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>最近交易（{detail.recent_orders.length} 笔）</div>
          {detail.recent_orders.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>数据同步中，请稍后查看</div>
          ) : (
            <div className="table-wrap">
              <table style={{ minWidth: 560 }}>
                <thead>
                  <tr>
                    <th>动作</th><th>数量</th><th>状态</th><th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.recent_orders.map((o) => (
                    <tr key={o.id}>
                      <td style={{ fontWeight: 600 }}>{o.action.toUpperCase()}</td>
                      <td>{o.qty}</td>
                      <td>{o.status === "filled" ? "成交" : o.status}</td>
                      <td>{o.executed_at ? new Date(o.executed_at).toLocaleString("zh-CN") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ★ 一键跟单模态（与策略广场一致） */}
      {followOpen && detail && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 420, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>跟单「{detail.display_name}」</div>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>Gate 合约 · 逐仓模式</div>
            <label className="label">跟单比例（%）</label>
            <input className="input" style={{ width: "100%", marginBottom: 12 }} type="number" value={form.percent} onChange={(e) => setForm({ ...form, percent: Number(e.target.value) })} />
            <label className="label">杠杆（1-125x）</label>
            <input className="input" style={{ width: "100%", marginBottom: 12 }} type="number" value={form.leverage} onChange={(e) => setForm({ ...form, leverage: Number(e.target.value) })} />
            <label className="label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={form.paper} onChange={(e) => setForm({ ...form, paper: e.target.checked })} />
              模拟盘（沙箱验证，不触达真实资金）
            </label>
            {formMsg && <div style={{ color: formMsg.includes("已创建") ? "var(--success)" : "var(--danger)", fontSize: 13, marginTop: 12 }}>{formMsg}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
              <button className="btn btn-secondary" onClick={() => { setFollowOpen(false); setFormMsg(""); }}>取消</button>
              <button className="btn btn-primary" onClick={createBot}>确认跟单</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
