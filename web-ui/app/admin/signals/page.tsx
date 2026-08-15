"use client";

import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import ExchangeTabs from "@/components/ExchangeTabs";

type TraderRow = {
  id: number;
  exchange: string;
  trader_id: string;
  name: string;
  roi_7d: number;
  roi_30d: number;
  roi_all: number;
  win_rate_all: number;
  max_drawdown: number;
  trading_days: number;
  followers: number;
};

type StrategyRow = TraderRow & {
  display_name: string;
  style: string;
  risk_rating: string;
  status: string;
};

type SearchResult = {
  leader_id: number | string;
  nick: string;
  roi_30d: number;
  win_rate_all: number;
  max_drawdown: number;
  followers: number;
  is_follow: boolean;
  is_full: boolean;
  style?: string;
  abstract?: string;
  markets?: string[];
  min_follow_amount?: string;
  max_follow_amount?: string;
};

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };

/** M2 信号源管理：5 所标签（T2.8）+ 待选池（T2.5）+ 已添加池 + G04 上架/暂停/下架（T2.6）。 */
export default function SignalsAdminPage() {
  const router = useRouter();
  const [exchange, setExchange] = useState("gate");
  const [pending, setPending] = useState<TraderRow[]>([]);
  const [listed, setListed] = useState<StrategyRow[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [showAdd, setShowAdd] = useState<TraderRow | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [style, setStyle] = useState("trend");
  const [risk, setRisk] = useState("mid");
  const [force, setForce] = useState(false);
  const [forceReason, setForceReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchKw, setSearchKw] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchMsg, setSearchMsg] = useState("");
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, l] = await Promise.all([
        apiFetch<{ items: TraderRow[] }>(`/v1/strategies/pending?exchange=${exchange}`, {}, tokenStore.access),
        apiFetch<{ items: StrategyRow[] }>(`/v1/strategies?exchange=${exchange}`, {}, undefined),
      ]);
      setPending(p.items);
      setListed(l.items.filter((x) => x.status !== "delisted"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载失败");
    }
  }, [exchange]);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function onAdd() {
    if (!showAdd) return;
    setLoading(true);
    setErr("");
    try {
      const res = await apiFetch<{ id: number; forced: boolean; failures: string[] }>(
        "/v1/strategies",
        {
          method: "POST",
          body: JSON.stringify({
            trader_id: showAdd.id,
            display_name: displayName || showAdd.trader_id,
            style,
            risk_rating: risk,
            exchange,
            force,
            force_reason: force ? forceReason : undefined,
          }),
        },
        tokenStore.access
      );
      setMsg(
        res.forced
          ? `已强制上架（原因：${forceReason || "未填写"}；跳过门槛：${res.failures.join("、")}）`
          : `策略「${displayName || showAdd.trader_id}」已上架`
      );
      setShowAdd(null);
      setForce(false);
      setForceReason("");
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "上架失败");
    } finally {
      setLoading(false);
    }
  }

  async function onStatus(id: number, status: string, name: string) {
    try {
      await apiFetch(`/v1/strategies/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }, tokenStore.access);
      setMsg(`「${name}」已${status === "paused" ? "暂停" : status === "delisted" ? "下架" : "恢复"}`);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function onSearch() {
    const kw = searchKw.trim();
    if (!kw) return;
    setSearching(true);
    setSearchMsg("");
    setErr("");
    try {
      const res = await apiFetch<{ ok: boolean; message?: string; items: SearchResult[]; source?: string }>(
        `/admin/v1/signal-session/search?keyword=${encodeURIComponent(kw)}`,
        {},
        tokenStore.adminAccess
      );
      if (!res.ok) {
        setSearchMsg(res.message || "搜索失败");
        setSearchResults([]);
      } else {
        setSearchResults(res.items);
        if (res.source === "detail") {
          setSearchMsg(res.items.length === 0 ? "未找到该 ID 对应的带单员" : `按 ID 精确查找到 1 个带单员`);
        } else {
          setSearchMsg(res.items.length === 0 ? "未找到匹配的带单员（昵称搜索；纯数字 ID 会按 ID 精确查）" : `找到 ${res.items.length} 个带单员`);
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "搜索失败");
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  const g04Pass = (r: TraderRow) => r.win_rate_all >= 55 && r.max_drawdown <= 30 && r.trading_days >= 30;

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>信号源管理</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>带单员审核 · ★G04 门槛：胜率≥55% / 回撤≤30% / 天数≥30</div>
        </div>

        <ExchangeTabs current={exchange} onChange={setExchange} />

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {/* 搜索带单员（只展示，不跟单） */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>搜索带单员 <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 12 }}>按昵称查 Gate 带单员画像，仅用于人工确认要跟单的对象</span></div>
          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            <input
              className="input"
              style={{ flex: 1, maxWidth: 360 }}
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSearch()}
              placeholder="输入带单员昵称，如：风懃"
            />
            <button className="btn btn-primary" onClick={onSearch} disabled={searching || !searchKw.trim()}>
              {searching ? "搜索中…" : "搜索"}
            </button>
          </div>
          {searchMsg && <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10 }}>{searchMsg}</div>}
          {searchResults !== null && searchResults.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                  <th style={th}>leader_id</th>
                  <th style={th}>昵称</th>
                  <th style={th}>30日收益</th>
                  <th style={th}>胜率</th>
                  <th style={th}>回撤</th>
                  <th style={th}>跟单人数</th>
                  <th style={th}>状态</th>
                </tr>
              </thead>
              <tbody>
                {searchResults.map((r) => (
                  <Fragment key={String(r.leader_id)}>
                    <tr style={{ borderTop: "1px solid var(--rule)" }}>
                      <td style={td}>{r.leader_id}</td>
                      <td style={{ ...td, fontWeight: 600 }}>{r.nick}</td>
                      <td style={td}>{r.roi_30d.toFixed(2)}%</td>
                      <td style={td}>{r.win_rate_all.toFixed(1)}%</td>
                      <td style={td}>{r.max_drawdown.toFixed(1)}%</td>
                      <td style={td}>{r.followers}</td>
                      <td style={td}>
                        {r.is_follow ? <span style={{ color: "var(--success)" }}>已跟单</span> : r.is_full ? <span style={{ color: "var(--warning)" }}>已满员</span> : <span style={{ color: "var(--muted)" }}>未跟单</span>}
                      </td>
                    </tr>
                    {r.style && (
                    <tr style={{ borderTop: "1px solid var(--rule)", background: "rgba(255,255,255,0.015)" }}>
                      <td colSpan={7} style={{ ...td, color: "var(--muted)", paddingTop: 6, paddingBottom: 6 }}>
                        <div style={{ lineHeight: 1.7 }}>
                          <div><b style={{ color: "var(--fg)" }}>风格</b>：{r.style.replace(/\|/g, " / ")}　<b style={{ color: "var(--fg)" }}>跟单区间</b>：{r.min_follow_amount || "-"} ~ {r.max_follow_amount || "-"} USDT</div>
                          {r.abstract && <div style={{ marginTop: 2 }}><b style={{ color: "var(--fg)" }}>简介</b>：{r.abstract}</div>}
                          {r.markets && r.markets.length > 0 && <div style={{ marginTop: 2 }}><b style={{ color: "var(--fg)" }}>交易标的</b>：{(r.markets as string[]).join("、")}</div>}
                        </div>
                      </td>
                    </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 待选池 */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>待选池（{pending.length}）</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                <th style={th}>ID</th>
                <th style={th}>名称</th>
                <th style={th}>7日收益</th>
                <th style={th}>累计收益</th>
                <th style={th}>胜率</th>
                <th style={th}>回撤</th>
                <th style={th}>天数</th>
                <th style={th}>门槛</th>
                <th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((t) => {
                const pass = g04Pass(t);
                return (
                  <tr key={t.id} style={{ borderTop: "1px solid var(--rule)" }}>
                    <td style={td}>{t.id}</td>
                    <td style={{ ...td, fontWeight: 600 }}>{t.trader_id}</td>
                    <td style={td}>{t.roi_7d.toFixed(1)}%</td>
                    <td style={td}>{t.roi_all.toFixed(1)}%</td>
                    <td style={td}>{t.win_rate_all.toFixed(1)}%</td>
                    <td style={td}>{t.max_drawdown.toFixed(1)}%</td>
                    <td style={td}>{t.trading_days}</td>
                    <td style={td}>
                      <span style={{ color: pass ? "var(--success)" : "var(--danger)" }}>{pass ? "达标" : "未达标"}</span>
                    </td>
                    <td style={td}>
                      <button className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12 }} onClick={() => setShowAdd(t)}>
                        上架
                      </button>
                    </td>
                  </tr>
                );
              })}
              {pending.length === 0 && (
                <tr><td colSpan={9} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无待选带单员（等待采集）</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* 已添加池 */}
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 12 }}>已添加池（{listed.length}）</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                <th style={th}>名称</th>
                <th style={th}>风格</th>
                <th style={th}>风险</th>
                <th style={th}>30日收益</th>
                <th style={th}>胜率</th>
                <th style={th}>状态</th>
                <th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {listed.map((s) => (
                <tr key={s.id} style={{ borderTop: "1px solid var(--rule)" }}>
                  <td style={{ ...td, fontWeight: 600 }}>{s.display_name}</td>
                  <td style={td}>{STYLE_LABEL[s.style] || s.style}</td>
                  <td style={td}>{s.risk_rating === "low" ? "低" : s.risk_rating === "mid" ? "中" : "高"}</td>
                  <td style={td}>{s.roi_30d.toFixed(1)}%</td>
                  <td style={td}>{s.win_rate_all.toFixed(1)}%</td>
                  <td style={td}>
                    <span style={{ color: s.status === "listed" ? "var(--success)" : s.status === "paused" ? "var(--warning)" : "var(--muted)" }}>
                      {s.status === "listed" ? "运行中" : s.status === "paused" ? "已暂停" : "已下架"}
                    </span>
                  </td>
                  <td style={td}>
                    {s.status === "listed" ? (
                      <button className="btn btn-secondary" style={{ padding: "5px 12px", fontSize: 12, marginRight: 6 }} onClick={() => onStatus(s.id, "paused", s.display_name)}>暂停</button>
                    ) : (
                      <button className="btn btn-secondary" style={{ padding: "5px 12px", fontSize: 12, marginRight: 6 }} onClick={() => onStatus(s.id, "listed", s.display_name)}>恢复</button>
                    )}
                    <button className="btn btn-secondary" style={{ padding: "5px 12px", fontSize: 12, color: "var(--danger)" }} onClick={() => onStatus(s.id, "delisted", s.display_name)}>下架</button>
                  </td>
                </tr>
              ))}
              {listed.length === 0 && (
                <tr><td colSpan={7} style={{ ...td, textAlign: "center", color: "var(--muted)", padding: 24 }}>暂无已添加策略</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 上架弹窗（G04） */}
      {showAdd && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.78)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 460, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>上架「{showAdd.trader_id}」</div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 16 }}>
              胜率 {showAdd.win_rate_all.toFixed(1)}% · 回撤 {showAdd.max_drawdown.toFixed(1)}% · {showAdd.trading_days} 天
              {!g04Pass(showAdd) && <span style={{ color: "var(--danger)" }}>（未达 ★G04 门槛）</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label className="label">前端展示名称</label>
                <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={showAdd.trader_id} />
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="label">风格</label>
                  <select className="input" value={style} onChange={(e) => setStyle(e.target.value)}>
                    <option value="trend">趋势</option>
                    <option value="range">震荡</option>
                    <option value="momentum">动量</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label className="label">风险评级</label>
                  <select className="input" value={risk} onChange={(e) => setRisk(e.target.value)}>
                    <option value="low">低风险</option>
                    <option value="mid">中风险</option>
                    <option value="high">高风险</option>
                  </select>
                </div>
              </div>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "var(--fg)" }}>
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                强制上架（跳过 G04 门槛，需填写理由留痕）
              </label>
              {force && (
                <input className="input" value={forceReason} onChange={(e) => setForceReason(e.target.value)} placeholder="强制上架理由（必填，写入审计日志）" />
              )}
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
              <button className="btn btn-secondary" onClick={() => setShowAdd(null)}>取消</button>
              <button className="btn btn-primary" onClick={onAdd} disabled={loading || (force && !forceReason)}>
                {loading ? "提交中…" : "确认上架"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
