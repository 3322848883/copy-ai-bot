"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Strategy = {
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
};

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };
const RISK_LABEL: Record<string, string> = { low: "低风险", mid: "中风险", high: "高风险" };
const RISK_COLOR: Record<string, string> = { low: "#28c464", mid: "#eab308", high: "#ef4444" };

/** M2 T2.9 策略广场：筛选 + 排序 + 一键跟单（M6 支持模拟盘）。 */
export default function StrategiesPage() {
  const router = useRouter();
  const [items, setItems] = useState<Strategy[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [style, setStyle] = useState("");
  const [risk, setRisk] = useState("");
  const [sort, setSort] = useState("roi_30d");
  const [err, setErr] = useState("");
  const [creating, setCreating] = useState<Strategy | null>(null);
  const [form, setForm] = useState({ percent: 20, leverage: 10, paper: false });
  const [formMsg, setFormMsg] = useState("");
  // ★ 分页
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 12;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (style) params.set("style", style);
    if (risk) params.set("risk_rating", risk);
    params.set("sort", sort);
    params.set("page", String(page));
    params.set("size", String(PAGE_SIZE));
    apiFetch<{ items: Strategy[]; total: number }>(`/v1/strategies?${params}`)
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [style, risk, sort, page]);

  async function createBot() {
    if (!creating) return;
    setFormMsg("");
    try {
      if (!tokenStore.access) {
        router.push("/login");
        return;
      }
      // 取用户已绑定的交易所 API key（未绑定提示去绑定）
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
            strategy_id: creating.id, exchange: "gate", api_key_id: gateKey.id,
            amount_mode: "percent", percent: form.percent, leverage: form.leverage,
            margin_mode: "isolated", paper: form.paper,
          }),
        },
        tokenStore.access
      );
      setFormMsg("跟单机器人已创建");
      setTimeout(() => setCreating(null), 900);
    } catch (e) {
      setFormMsg(e instanceof Error ? e.message : "创建失败");
    }
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 26, fontWeight: 700 }}>策略广场</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 6 }}>
            已通过严格审核的带单策略 · 共 {total} 个
          </div>
        </div>

        {/* 筛选排序栏（T2.9） */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
          <select className="input" style={{ width: 140 }} value={style} onChange={(e) => { setStyle(e.target.value); setPage(1); }}>
            <option value="">全部风格</option>
            <option value="trend">趋势</option>
            <option value="range">震荡</option>
            <option value="momentum">动量</option>
          </select>
          <select className="input" style={{ width: 140 }} value={risk} onChange={(e) => setRisk(e.target.value)}>
            <option value="">全部风险</option>
            <option value="low">低风险</option>
            <option value="mid">中风险</option>
            <option value="high">高风险</option>
          </select>
          <select className="input" style={{ width: 170 }} value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
            <option value="followers">按跟单人数</option>
            <option value="roi_7d">按 7 日收益</option>
            <option value="roi_30d">按 30 日收益</option>
            <option value="roi_all">按累计收益</option>
            <option value="win_rate_all">按胜率</option>
          </select>
        </div>

        {err && <div className="error-box">{err}</div>}
        {loading ? (
          <div style={{ color: "var(--muted)", padding: 40, textAlign: "center" }}>加载中…</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {items.map((s) => (
              <Link
                key={s.id}
                href={`/strategies/${s.id}`}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <div className="card" style={{ height: "100%", transition: "border-color .2s", cursor: "pointer" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 16 }}>{s.display_name}</div>
                      <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>
                        {STYLE_LABEL[s.style] || s.style}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: 12, padding: "3px 10px", borderRadius: 20,
                        background: `${RISK_COLOR[s.risk_rating]}22`, color: RISK_COLOR[s.risk_rating],
                        border: `1px solid ${RISK_COLOR[s.risk_rating]}55`,
                      }}
                    >
                      {RISK_LABEL[s.risk_rating]}
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 13 }}>
                    <div><span style={{ color: "var(--muted)" }}>30日收益</span><br /><strong style={{ color: s.roi_30d >= 0 ? "var(--success)" : "var(--danger)" }}>{s.roi_30d.toFixed(1)}%</strong></div>
                    <div><span style={{ color: "var(--muted)" }}>累计收益</span><br /><strong style={{ color: s.roi_all >= 0 ? "var(--success)" : "var(--danger)" }}>{s.roi_all.toFixed(1)}%</strong></div>
                    <div><span style={{ color: "var(--muted)" }}>胜率</span><br /><strong>{s.win_rate_all.toFixed(1)}%</strong></div>
                    <div><span style={{ color: "var(--muted)" }}>跟单人数</span><br /><strong>{s.followers}</strong></div>
                  </div>
                  {s.status === "listed" && (
                    <button
                      className="btn btn-primary"
                      style={{ width: "100%", marginTop: 14 }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setCreating(s);
                        setFormMsg("");
                      }}
                    >
                      开始跟单
                    </button>
                  )}
                </div>
              </Link>
            ))}
            {items.length === 0 && (
              <div style={{ color: "var(--muted)", gridColumn: "1/-1", textAlign: "center", padding: 40 }}>
                暂无策略，请稍后再来
              </div>
            )}
          </div>
        )}

        {/* ★ 分页 */}
        {!loading && totalPages > 1 && (
          <div style={{ display: "flex", justifyContent: "center", gap: 8, alignItems: "center", paddingTop: 24 }}>
            <button className="btn btn-secondary" style={{ padding: "6px 16px", fontSize: 13 }} disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
            <span style={{ fontSize: 13, color: "var(--muted)", margin: "0 8px" }}>第 {page} / {totalPages} 页 · 共 {total} 个策略</span>
            <button className="btn btn-secondary" style={{ padding: "6px 16px", fontSize: 13 }} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
          </div>
        )}

        {/* M6：一键跟单创建模态（支持模拟盘） */}
        {creating && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ width: 420, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>跟单「{creating.display_name}」</div>
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
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
                <button className="btn btn-secondary" onClick={() => setCreating(null)}>取消</button>
                <button className="btn btn-primary" onClick={createBot}>创建机器人</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
