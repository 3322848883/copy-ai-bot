"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Sparkline } from "@/components/Sparkline";
import FollowModal from "@/components/FollowModal";

type SparkPoint = { date: string; value: number };

type Strategy = {
  id: number;
  exchange: string;
  display_name: string;
  style: string;
  risk_rating: string;
  status: string;
  roi_7d: number;
  roi_30d: number;
  roi_90d: number;
  roi_all: number;
  sparkline?: SparkPoint[];
  roi_source?: "profit_chart" | "leader_detail" | "none";
  win_rate_all: number;
  max_drawdown: number;
  trading_days: number;
  followers: number;
  source?: string;
  hide_position?: boolean | null;
  follow_enabled?: boolean;
};

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };
const STYLE_TAG: Record<string, string> = { trend: "tag-trend", range: "tag-range", momentum: "tag-momentum" };
const RISK_SHORT: Record<string, string> = { low: "低", mid: "中", high: "高" };
const RISK_COLOR: Record<string, string> = { low: "#28c464", mid: "#eab308", high: "#ef4444" };

const STYLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部" },
  { value: "trend", label: "趋势" },
  { value: "range", label: "震荡" },
  { value: "momentum", label: "动量" },
];
const RISK_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部" },
  { value: "low", label: "低" },
  { value: "mid", label: "中" },
  { value: "high", label: "高" },
];
const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "followers", label: "跟单人数" },
  { value: "roi_7d", label: "7日收益" },
  { value: "roi_30d", label: "30日收益" },
  { value: "roi_all", label: "累计收益" },
  { value: "win_rate_all", label: "累计胜率" },
];

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

/** 页码式分页：1 … 当前±1 … N（总页数 ≤7 时全显）。 */
function pageNumbers(current: number, total: number): Array<number | "…"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: Array<number | "…"> = [1];
  if (current > 3) out.push("…");
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) out.push(i);
  if (current < total - 2) out.push("…");
  out.push(total);
  return out;
}

/** M2 T2.9 策略广场（对齐设计稿）：页眉 eyebrow + chip 胶囊筛选 + 卡片迷你 spark +
 *  底部信息行（跟单人数/7日收益 + 开启跟单/查看详情）+ 页码式分页 + 一键跟单（M6 模拟盘）。 */
export default function StrategiesPage() {
  const [items, setItems] = useState<Strategy[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [style, setStyle] = useState("");
  const [risk, setRisk] = useState("");
  const [sort, setSort] = useState("followers");
  const [err, setErr] = useState("");
  const [creating, setCreating] = useState<Strategy | null>(null);
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

  function pickSort(v: string) {
    setSort(v);
    setPage(1);
  }

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <style>{`
        .saas-scard { display: block; border-radius: 10px; transition: transform .2s ease, box-shadow .2s ease; }
        .saas-scard:hover { transform: translateY(-3px); box-shadow: 0 12px 28px rgba(0,0,0,.38), 0 0 22px rgba(0,212,170,.16); }
        .saas-scard:hover .card { border-color: rgba(0,212,170,.55); }
      `}</style>

      <div className="page-wrap">
        {/* 页头（设计稿：eyebrow + 28px 标题） */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">STRATEGY PLAZA · 策略广场</div>
            <h1 className="page-title">
              策略广场<small>精选聚合策略 · 数据实时同步</small>
            </h1>
          </div>
        </div>

        {/* chip 胶囊筛选条（风格 / 风险 / 排序，替换原 select） */}
        <div className="filter-bar">
          <span className="fb-label">风格</span>
          {STYLE_OPTIONS.map((o) => (
            <button
              key={`s-${o.value}`}
              className={`chip ${style === o.value ? "active" : ""}`}
              onClick={() => { setStyle(o.value); setPage(1); }}
            >
              {o.label}
            </button>
          ))}
          <div className="filter-sep" />
          <span className="fb-label">风险</span>
          {RISK_OPTIONS.map((o) => (
            <button
              key={`r-${o.value}`}
              className={`chip ${risk === o.value ? "active" : ""}`}
              onClick={() => { setRisk(o.value); setPage(1); }}
              style={o.value === "high" && risk === "high" ? { background: "rgba(239,68,68,0.12)", borderColor: "rgba(239,68,68,0.5)", color: "#f87171" } : undefined}
            >
              {o.label}
            </button>
          ))}
          <div className="filter-sep" />
          <span className="fb-label">排序</span>
          {SORT_OPTIONS.map((o) => (
            <button
              key={`o-${o.value}`}
              className={`chip ${sort === o.value ? "active" : ""}`}
              onClick={() => pickSort(o.value)}
            >
              {o.label}
            </button>
          ))}
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontFamily: "var(--font-geist-mono)" }}>
            共 {total} 个策略
          </span>
        </div>

        {err && <div className="error-box">{err}</div>}

        {loading ? (
          <div style={{ color: "var(--muted)", padding: 40, textAlign: "center" }}>加载中…</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
            {items.map((s) => {
              const hasRoi = s.roi_source !== "none";
              const up = hasRoi && s.roi_30d >= 0;
              const sparkVals = (s.sparkline ?? []).map((p) => p.value);
              const roiColor = (v: number) => (!hasRoi ? "var(--muted)" : v >= 0 ? "var(--success)" : "var(--danger)");
              const roiText = (v: number) => (!hasRoi ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);
              return (
                <Link
                  key={s.id}
                  href={`/strategies/${s.id}`}
                  className="saas-scard"
                  style={{ textDecoration: "none", color: "inherit", height: "100%" }}
                >
                  <div className="card" style={{ height: "100%", display: "flex", flexDirection: "column", gap: 16, position: "relative", overflow: "hidden", cursor: "pointer" }}>
                    {/* 角落信号光晕 */}
                    <div
                      style={{
                        position: "absolute", bottom: -24, right: -24, width: 110, height: 110, borderRadius: "50%", pointerEvents: "none",
                        background: up ? "radial-gradient(circle, rgba(0,212,170,0.09), transparent 70%)" : "radial-gradient(circle, rgba(239,68,68,0.07), transparent 70%)",
                      }}
                    />
                    {/* 顶部：名称 + 风格彩色标签（tag-trend/range/momentum） */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, position: "relative" }}>
                      <div style={{ fontWeight: 600, fontSize: 16 }}>{s.display_name}</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                        {s.followers >= 1000 && <span className="badge badge-ok">热门</span>}
                        <span className={`tag ${STYLE_TAG[s.style] ?? ""}`}>{STYLE_LABEL[s.style] ?? s.style}</span>
                      </div>
                    </div>
                    {/* 2×2 指标：30日收益 / 7日收益 / 累计收益 / 累计胜率（★ 与收益曲线同源同口径） */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>30日收益</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 17, fontWeight: 600, color: roiColor(s.roi_30d), marginTop: 2 }}>{roiText(s.roi_30d)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>7日收益</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 17, fontWeight: 600, color: roiColor(s.roi_7d), marginTop: 2 }}>{roiText(s.roi_7d)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>累计收益</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 17, fontWeight: 600, color: roiColor(s.roi_all), marginTop: 2 }}>{roiText(s.roi_all)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>累计胜率</div>
                        <div style={{ fontFamily: "var(--font-geist-mono)", fontSize: 17, fontWeight: 600, marginTop: 2 }}>{s.win_rate_all.toFixed(1)}%</div>
                      </div>
                    </div>
                    {/* 迷你收益曲线 spark（★ 真实每日累计序列，与详情页收益曲线同源） */}
                    <div style={{ height: 52, position: "relative" }}>
                      {sparkVals.length >= 2 ? (
                        <Sparkline id={`${s.id}`} values={sparkVals} />
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", fontSize: 11, color: "var(--muted)" }}>
                          暂无收益数据
                        </div>
                      )}
                    </div>
                    {/* 底部信息行：跟单人数 + 风险评级 + 数据源标注 + 开启跟单/查看详情小按钮 */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid rgba(51,65,85,0.4)", position: "relative" }}>
                      <span style={{ fontSize: 12, color: "var(--muted)" }}>
                        <span style={{ color: "var(--tertiary)", marginRight: 6 }}>◉</span>
                        {fmt(s.followers)} 人跟单
                        <span style={{ marginLeft: 8, color: RISK_COLOR[s.risk_rating] ?? "var(--muted)" }}>
                          · {RISK_SHORT[s.risk_rating] ?? s.risk_rating}风险
                        </span>
                        {s.roi_source === "leader_detail" && (
                          <span style={{ marginLeft: 8, fontSize: 10, color: "var(--tertiary)", border: "1px solid var(--rule)", borderRadius: 999, padding: "1px 8px" }}>详情口径</span>
                        )}
                      </span>
                      {s.status === "listed" ? (
                        s.follow_enabled === false ? (
                          /* ★ 阀门上移后台管理员：未开放跟单的策略展示友好提示 */
                          <span
                            className="btn btn-secondary"
                            style={{
                              padding: "6px 14px", fontSize: 12, pointerEvents: "none",
                              borderStyle: "dashed", opacity: 0.75,
                            }}
                          >
                            暂未开放跟单
                          </span>
                        ) : (
                          <button
                            className="btn btn-primary"
                            style={{ padding: "6px 14px", fontSize: 12 }}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setCreating(s);
                            }}
                          >
                            开启跟单
                          </button>
                        )
                      ) : (
                        <span className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12, pointerEvents: "none" }}>
                          查看详情
                        </span>
                      )}
                    </div>
                  </div>
                </Link>
              );
            })}
            {items.length === 0 && (
              <div style={{ color: "var(--muted)", gridColumn: "1/-1", textAlign: "center", padding: 40 }}>
                暂无策略，请稍后再来
              </div>
            )}
          </div>
        )}

        {/* 页码式分页（page-btn） */}
        {!loading && totalPages > 1 && (
          <div className="pagination" style={{ justifyContent: "center", marginTop: 24 }}>
            <button className="page-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
            {pageNumbers(page, totalPages).map((n, i) =>
              n === "…" ? (
                <span key={`e${i}`} style={{ color: "var(--tertiary)", fontSize: 12, fontFamily: "var(--font-geist-mono)", padding: "0 2px" }}>…</span>
              ) : (
                <button key={n} className={`page-btn ${n === page ? "active" : ""}`} onClick={() => setPage(n)}>{n}</button>
              )
            )}
            <button className="page-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>›</button>
          </div>
        )}

        {/* ★ 跟单弹窗（与策略详情共用 FollowModal，设置完全一致） */}
        <FollowModal
          strategy={creating ? { id: creating.id, display_name: creating.display_name, style: creating.style, max_drawdown: creating.max_drawdown } : null}
          onClose={() => setCreating(null)}
        />
      </div>
    </main>
  );
}
