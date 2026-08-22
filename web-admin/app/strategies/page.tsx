"use client";

import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type Strategy = {
  id: number; trader_id: number; exchange: string; display_name: string; style: string; risk_rating: string;
  status: string; followers: number; roi_30d: number; roi_all: number; win_rate_30d: number; win_rate_all: number;
  max_drawdown: number; trading_days: number; collector_ready?: boolean;
  hide_position?: boolean | null;
  is_follow?: boolean; created_at?: string;
};
type Trader = {
  id: number; exchange: string; trader_id: string; name: string; roi_7d: number; roi_30d: number; roi_all: number;
  win_rate_all: number; max_drawdown: number; trading_days: number; followers: number; collector_ready?: boolean;
  hide_position?: boolean | null;
};
type SearchResult = {
  leader_id: number | string; nick: string; roi_30d: number; win_rate_all: number; max_drawdown: number;
  followers: number; is_follow: boolean; is_full: boolean; style?: string; abstract?: string;
  markets?: string[]; min_follow_amount?: string; max_follow_amount?: string;
  hide_position?: boolean | null;
};

const EXCHANGES = ["全部", "GATE", "BINANCE", "OKX", "BYBIT", "BITGET"];
const STYLE_OPTIONS = [
  { v: "trend", label: "趋势" },
  { v: "range", label: "震荡" },
  { v: "momentum", label: "动量" },
];
const RISK_OPTIONS = [
  { v: "low", label: "低" },
  { v: "mid", label: "中" },
  { v: "high", label: "高" },
];

/** G04 门槛：胜率≥55% · 回撤≤30% · 带单≥30天 */
function gatePassed(t: { win_rate_all: number; max_drawdown: number; trading_days: number }) {
  return t.win_rate_all >= 55 && t.max_drawdown <= 30 && t.trading_days >= 30;
}
function gateFailures(t: { win_rate_all: number; max_drawdown: number; trading_days: number }) {
  const out: string[] = [];
  if (t.win_rate_all < 55) out.push("胜率不足");
  if (t.max_drawdown > 30) out.push("回撤超标");
  if (t.trading_days < 30) out.push("天数不足");
  return out;
}

/** 仓位公开状态徽章：公开→模式A 可用；隐藏→仅模式B（API 镜像跟单）；null→未采集 */
function PosBadge({ hide }: { hide?: boolean | null }) {
  if (hide === true)
    return <span className="badge badge-warn" title="带单员隐藏当前持仓：公开采集拿不到仓位，上架请使用模式B（绑定API镜像跟单）">隐藏</span>;
  if (hide === false) return <span className="badge badge-ok" title="当前持仓公开：模式A（广场采集）可用">公开</span>;
  return <span className="badge badge-muted" title="尚未采集到持仓公开状态（detail 未拉过）">未知</span>;
}

/** M5 T5.4 信号源审核：交易所 Tab + G04 门槛 + 上架/强制上架 + G26 运维看板。 */
export default function AdminStrategiesPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const [ex, setEx] = useState("全部");
  const [listed, setListed] = useState<Strategy[]>([]);
  const [pending, setPending] = useState<Trader[]>([]);
  const [session, setSession] = useState<{ state?: string; follow_count?: number } | null>(null);

  // 上架弹窗状态
  const [listTarget, setListTarget] = useState<Trader | null>(null);
  const [style, setStyle] = useState("trend");
  const [riskRating, setRiskRating] = useState("mid");
  const [forceReason, setForceReason] = useState("");
  const [delistTarget, setDelistTarget] = useState<Strategy | null>(null);

  const [searchKw, setSearchKw] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchMsg, setSearchMsg] = useState("");
  const [searching, setSearching] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // ★ M6 T8 设为数据源（进入审核流水线）：手动新增待选带单员 + 搜索结果导入
  const [impEx, setImpEx] = useState("gate");
  const [impId, setImpId] = useState("");
  const [impName, setImpName] = useState("");
  const [importing, setImporting] = useState(false);

  async function importSource(exchange: string, traderId: string, name?: string) {
    if (!traderId) return;
    setImporting(true);
    try {
      const r = await apiFetch<{ ok: boolean; message?: string; already_listed?: boolean; collector_ready?: boolean }>(
        "/admin/v1/signals/import",
        { method: "POST", body: JSON.stringify({ exchange, trader_id: traderId, name: name || "", followers: 0 }) },
        tokenStore.adminAccess,
      );
      toast(r.ok ? "success" : "warn", r.message || (r.ok ? "已加入待选池，请在待选池完成审核上架" : "导入失败"));
      setImpId("");
      setImpName("");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }

  const importFromSearch = (r: SearchResult) =>
    importSource("gate", String(r.leader_id), r.nick);

  const collectorTag = (t: { exchange?: string; collector_ready?: boolean }) =>
    t.collector_ready === false ? <span className="badge badge-warn">待接入采集</span> : null;

  async function syncProfiles() {
    setSyncing(true);
    try {
      const r = await apiFetch<{ mode: string; async?: boolean; task_id?: string; count?: number; note?: string }>(
        "/admin/v1/signals/sync",
        { method: "POST", body: JSON.stringify({}) },
        tokenStore.adminAccess,
      );
      toast("success", r.async ? "已触发全量画像同步（后台任务）" : `画像同步完成：${r.count ?? 0} 个带单员`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "同步失败");
    } finally {
      setSyncing(false);
    }
  }

  const load = useCallback(async () => {
    try {
      const [l, p, s] = await Promise.all([
        apiFetch<{ items: Strategy[] }>("/admin/v1/signals", {}, tokenStore.adminAccess),
        apiFetch<{ items: Trader[] }>("/admin/v1/signals/pending", {}, tokenStore.adminAccess),
        apiFetch<{ state?: string; follow_count?: number }>("/admin/v1/signal-session/status", {}, tokenStore.adminAccess).catch(() => ({})),
      ]);
      setListed(l.items);
      setPending(p.items);
      setSession(s);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  const pendingFiltered = ex === "全部" ? pending : pending.filter((t) => (t.exchange || "gate").toUpperCase() === ex);
  const listedFiltered = ex === "全部" ? listed : listed.filter((s) => (s.exchange || "gate").toUpperCase() === ex);

  async function setStatus(s: Strategy, status: string) {
    const label = status === "paused" ? "暂停" : status === "delisted" ? "下架" : "恢复";
    const ok = await confirm({
      title: `${label}策略`,
      message: `「${s.display_name}」${label}后将影响其下跟单机器人，确认${label}？`,
      danger: status !== "listed",
      confirmText: label,
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/signals/${s.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }, tokenStore.adminAccess);
      toast("success", `「${s.display_name}」已${label}`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function doList() {
    if (!listTarget) return;
    const passed = gatePassed(listTarget);
    const ok = await confirm({
      title: passed ? "确认上架？" : "强制上架（G04 豁免）",
      message: passed
        ? `「${listTarget.trader_id}」已通过 G04 门槛校验，上架后将出现在用户端策略广场`
        : `「${listTarget.trader_id}」未通过门槛（${gateFailures(listTarget).join(" / ")}）\n强制上架必须填写原因，并将写入审计日志`,
      danger: !passed,
      confirmText: passed ? "确认上架" : "强制上架",
    });
    if (!ok) return;
    try {
      const r = await apiFetch<{ id: number }>("/admin/v1/signals", {
        method: "POST",
        body: JSON.stringify({
          trader_id: listTarget.id,
          exchange: (ex === "全部" ? "gate" : ex.toLowerCase()),
          style,
          risk_rating: riskRating,
          force: !passed,
          force_reason: passed ? "" : forceReason,
        }),
      }, tokenStore.adminAccess);
      toast("success", passed ? `已上架 #${r.id} · G04 校验通过 · 已写入审计日志` : `已强制上架 #${r.id}（G04 留痕）`);
      setListTarget(null);
      setForceReason("");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "上架失败");
    }
  }

  async function doDelist() {
    if (!delistTarget) return;
    const ok = await confirm({
      title: "确认下架？",
      message: `下架「${delistTarget.display_name}」后：策略广场不再展示，已有跟单机器人暂停开仓，可正常平仓。`,
      danger: true,
      confirmText: "确认下架",
    });
    if (!ok) return;
    try {
      await apiFetch(`/admin/v1/signals/${delistTarget.id}/status`, { method: "PATCH", body: JSON.stringify({ status: "delisted" }) }, tokenStore.adminAccess);
      toast("success", `「${delistTarget.display_name}」已下架`);
      setDelistTarget(null);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "下架失败");
    }
  }

  async function onSearch() {
    const kw = searchKw.trim();
    if (!kw) return;
    setSearching(true);
    setSearchMsg("");
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
          setSearchMsg(res.items.length === 0 ? "未找到该 ID 对应的带单员" : "按 ID 精确查找到 1 个带单员");
        } else {
          setSearchMsg(res.items.length === 0 ? "未找到匹配的带单员（昵称搜索；纯数字 ID 会按 ID 精确查）" : `找到 ${res.items.length} 个带单员`);
        }
      }
    } catch (e) {
      setSearchMsg(e instanceof Error ? e.message : "搜索失败");
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  const riskBadge = (r: string) =>
    r === "high" ? <span className="badge badge-err">高</span> : r === "low" ? <span className="badge badge-ok">低</span> : <span className="badge badge-warn">中</span>;

  const statusBadge = (s: string) =>
    s === "listed" ? <span className="badge badge-ok">已上架</span> : s === "paused" ? <span className="badge badge-warn">已暂停</span> : <span className="badge badge-muted">已下架</span>;

  return (
    <div>
      {/* 同步画像 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">SIGNAL REVIEW · 信号源审核</div>
          <h1 className="page-title">信号源审核<small>{pendingFiltered.length} 待审 · G04 门槛校验</small></h1>
        </div>
        <button className="btn btn-secondary" onClick={syncProfiles} disabled={syncing}>
          {syncing ? "同步中…" : "同步画像"}
        </button>
      </div>

      {/* 交易所 Tab */}
      <div className="ex-tabs">
        {EXCHANGES.map((e) => (
          <button key={e} className={`ex-tab${ex === e ? " active" : ""}`} onClick={() => setEx(e)}>{e}</button>
        ))}
      </div>

      {/* 待选池 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>待选池（候选带单员）</div>
          <span className="panel-sub">/admin/v1/signals/pending · 门槛：胜率≥55% · 回撤≤30% · 带单≥30天（G04） · 仓位：公开→模式A可用，隐藏→仅模式B</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th className="num">#</th><th>带单员</th><th>仓位</th><th className="num">胜率</th><th className="num">最大回撤</th><th className="num">带单天数</th><th>门槛</th><th className="num">跟单人数</th><th>操作</th></tr>
            </thead>
            <tbody>
              {pendingFiltered.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--muted)" }}>暂无待选带单员</td></tr>
              )}
              {pendingFiltered.map((t, idx) => {
                const passed = gatePassed(t);
                const fails = gateFailures(t);
                return (
                  <tr key={t.id}>
                    <td className="num" style={{ color: "var(--muted)", fontSize: 12 }}>{idx + 1}</td>
                    <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>
                      {t.name}
                      <span style={{ marginLeft: 8, color: "var(--muted)", fontFamily: "inherit", fontSize: 11 }}>
                        · {t.exchange.toUpperCase()}
                      </span>
                      {collectorTag(t)}
                    </td>
                    <td><PosBadge hide={t.hide_position} /></td>
                    <td className="num" style={{ color: t.win_rate_all >= 55 ? "var(--success)" : "#f87171" }}>{t.win_rate_all.toFixed(1)}%</td>
                    <td className="num" style={{ color: t.max_drawdown > 30 ? "#f87171" : undefined }}>{t.max_drawdown.toFixed(1)}%</td>
                    <td className="num" style={{ color: t.trading_days < 30 ? "#f87171" : undefined }}>{t.trading_days}</td>
                    <td>
                      {passed
                        ? <span className="thresh pass">✓ 通过</span>
                        : <span className="thresh fail">✕ {fails.join(" / ")}</span>}
                    </td>
                    <td className="num">{t.followers || 0}</td>
                    <td>
                      <button
                        className={`action-link${passed ? "" : " danger"}`}
                        onClick={() => { setListTarget(t); setStyle("trend"); setRiskRating("mid"); setForceReason(""); }}
                      >
                        {passed ? "上架" : "强制上架"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 新增待选带单员（★ M6 T8 设为数据源 · 进入审核流水线 · 对应5家交易所） */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>新增待选带单员（设为数据源）</div>
          <span className="panel-sub">/admin/v1/signals/import · 写入该交易所待选池 → 审核上架 → 用户建机器人</span>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <select className="select" style={{ width: 150 }} value={impEx} onChange={(e) => setImpEx(e.target.value.toLowerCase())}>
            {EXCHANGES.filter((e) => e !== "全部").map((e) => (
              <option key={e} value={e.toLowerCase()}>{e} {e === "GATE" ? "" : "(待接入采集)"}</option>
            ))}
          </select>
          <input className="input" style={{ flex: 1, maxWidth: 220 }} placeholder="带单员 ID（如 Gate leader_id）" value={impId} onChange={(e) => setImpId(e.target.value)} />
          <input className="input" style={{ flex: 1, maxWidth: 260 }} placeholder="昵称（可选）" value={impName} onChange={(e) => setImpName(e.target.value)} />
          <button className="btn btn-primary" onClick={() => importSource(impEx, impId.trim(), impName.trim())} disabled={importing || !impId.trim()}>
            {importing ? "导入中…" : "加入待选池"}
          </button>
        </div>
        <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
          提示：仅 GATE 已接入信号源采集（搜索结果「设为数据源」也可直接导入）；其余交易所为人工录入待选池，上架后进入该所策略，采集待接入。
        </div>
      </div>

      {/* 已添加池 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>已添加池（线上策略）</div>
          <span className="panel-sub">/admin/v1/signals · add/pause/resume/delist</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th className="num">#</th><th>策略名</th><th>仓位</th><th>风格</th><th>风险</th><th className="num">30日收益</th><th className="num">跟单人数</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {listedFiltered.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--muted)" }}>暂无已上架策略</td></tr>
              )}
              {listedFiltered.map((s, idx) => (
                <tr key={s.id}>
                  <td className="num" style={{ color: "var(--muted)", fontSize: 12 }}>{idx + 1}</td>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>
                    {s.display_name}
                    {s.is_follow && <span className="badge badge-ok" style={{ marginLeft: 8, fontSize: 10 }}>已跟单</span>}
                    {collectorTag(s)}
                  </td>
                  <td><PosBadge hide={s.hide_position} /></td>
                  <td>{STYLE_OPTIONS.find((o) => o.v === s.style)?.label || s.style}</td>
                  <td>{riskBadge(s.risk_rating)}</td>
                  <td className="num" style={{ color: s.roi_30d >= 0 ? "var(--success)" : "#f87171" }}>{s.roi_30d >= 0 ? "+" : ""}{s.roi_30d.toFixed(1)}%</td>
                  <td className="num">{s.followers || 0}</td>
                  <td>{statusBadge(s.status)}</td>
                  <td>
                    {s.status === "listed" ? (
                      <button className="action-link" onClick={() => setStatus(s, "paused")}>暂停</button>
                    ) : s.status === "paused" ? (
                      <button className="action-link" onClick={() => setStatus(s, "listed")}>恢复</button>
                    ) : (
                      <button className="action-link" onClick={() => setStatus(s, "listed")}>重新上架</button>
                    )}
                    {" · "}
                    <button className="action-link danger" onClick={() => setDelistTarget(s)}>下架</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* G26 运维看板 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>运维看板</div>
          <span className="panel-sub">信号源采集会话 · 模式 A</span>
        </div>
        <div className="ops-grid">
          <div className="ops-card">
            <div className="ops-head">
              <span className="ops-name">信号源会话</span>
              <span className="badge badge-info">模式 A · 爬虫</span>
            </div>
            <div className="ops-grid2">
              <div><div className="ops-f">会话状态</div><div className="ops-v">{session?.state || "—"}</div></div>
              <div><div className="ops-f">跟单数</div><div className="ops-v">{session?.follow_count ?? "—"}</div></div>
              <div><div className="ops-f">采集状态</div><div className="ops-v"><span className={`ws-dot ${session?.state === "logged_in" ? "ws-online" : session?.state ? "ws-reconnect" : "ws-offline"}`}></span> {session?.state === "logged_in" ? "在线" : session?.state ? "连接中" : "未启动"}</div></div>
            </div>
          </div>
        </div>
      </div>

      {/* 搜索带单员（只展示，不跟单） */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>搜索带单员</div>
          <span className="panel-sub">signal-session/search · 按昵称/ID 查画像，仅用于人工确认</span>
        </div>
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
          <div style={{ overflowX: "auto" }}>
            <table className="ftx-table">
              <thead>
                <tr><th className="num">#</th><th>leader_id</th><th>昵称</th><th>仓位</th><th className="num">30日收益</th><th className="num">胜率</th><th className="num">回撤</th><th className="num">跟单人数</th><th>状态</th><th>操作</th></tr>
              </thead>
              <tbody>
                {searchResults.map((r, idx) => (
                  <Fragment key={String(r.leader_id)}>
                    <tr>
                      <td className="num" style={{ color: "var(--muted)", fontSize: 12 }}>{idx + 1}</td>
                      <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{r.leader_id}</td>
                      <td style={{ fontWeight: 600 }}>{r.nick}</td>
                      <td><PosBadge hide={r.hide_position} /></td>
                      <td className="num">{r.roi_30d.toFixed(2)}%</td>
                      <td className="num">{r.win_rate_all.toFixed(1)}%</td>
                      <td className="num">{r.max_drawdown.toFixed(1)}%</td>
                      <td className="num">{r.followers}</td>
                      <td>
                        {r.is_follow ? <span style={{ color: "var(--success)" }}>已跟单</span> : r.is_full ? <span style={{ color: "var(--warning)" }}>已满员</span> : <span style={{ color: "var(--muted)" }}>未跟单</span>}
                      </td>
                      <td>
                        <button className="action-link" disabled={importing} onClick={() => importFromSearch(r)}>
                          设为数据源
                        </button>
                      </td>
                    </tr>
                    {r.style && (
                      <tr style={{ background: "rgba(255,255,255,0.015)" }}>
                        <td colSpan={10} style={{ color: "var(--muted)", paddingTop: 6, paddingBottom: 6 }}>
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
          </div>
        )}
      </div>

      {/* 上架 / 强制上架弹窗 */}
      {listTarget && (
        <div className="modal-overlay">
          <div className={`modal${gatePassed(listTarget) ? "" : " danger"}`}>
            <div className="modal-hdr">
              <div className="modal-title" style={{ color: gatePassed(listTarget) ? undefined : "#f87171" }}>
                {gatePassed(listTarget) ? "确认上架？" : "强制上架（G04 豁免）"}
              </div>
              <button className="modal-close" onClick={() => setListTarget(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              {gatePassed(listTarget) ? (
                <><strong style={{ color: "var(--fg)" }}>{listTarget.name}</strong> 已通过 G04 门槛校验，上架后将出现在用户端策略广场</>
              ) : (
                <><strong style={{ color: "#f87171" }}>{listTarget.name}</strong> 未通过门槛校验（{gateFailures(listTarget).join(" / ")}）。强制上架必须填写原因，并将写入审计日志。</>
              )}
              <div style={{ marginTop: 6 }}>
                {listTarget.hide_position === true ? (
                  <span style={{ color: "var(--warning)" }}>⚠ 该带单员隐藏当前持仓：模式A（公开广场采集）拿不到其仓位信号，上架后仅支持模式B（绑定API镜像跟单）。</span>
                ) : listTarget.hide_position === false ? (
                  <span style={{ color: "var(--success)" }}>✓ 该带单员公开当前持仓：模式A（公开广场采集）可用。</span>
                ) : (
                  <span>仓位公开状态未知（尚未采集）。</span>
                )}
              </div>
            </div>
            {!gatePassed(listTarget) && (
              <div className="warn-note"><span>⚠</span><span>强制上架绕过 G04 门槛，将承担额外的信号质量风险，请审慎操作</span></div>
            )}
            <div className="field">
              <label className="field-label">策略名称（统一标准：昵称（id））</label>
              <div className="input" style={{ opacity: 0.75 }}>{listTarget.name}</div>
            </div>
            <div className="field" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label className="field-label">风格</label>
                <select className="select" value={style} onChange={(e) => setStyle(e.target.value)}>
                  {STYLE_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label">风险评级</label>
                <select className="select" value={riskRating} onChange={(e) => setRiskRating(e.target.value)}>
                  {RISK_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
              </div>
            </div>
            {!gatePassed(listTarget) && (
              <div className="field">
                <label className="field-label">强制上架原因（必填）</label>
                <textarea className="input" placeholder="例：实盘观察 2 周，胜率波动系短线止损策略导致…" value={forceReason} onChange={(e) => setForceReason(e.target.value)} />
              </div>
            )}
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setListTarget(null)}>取消</button>
              <button
                className={`btn ${gatePassed(listTarget) ? "btn-primary" : "btn-danger"}`}
                style={{ flex: 1 }}
                onClick={doList}
                disabled={!gatePassed(listTarget) && !forceReason}
              >
                {gatePassed(listTarget) ? "确认上架" : "强制上架"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 下架弹窗 */}
      {delistTarget && (
        <div className="modal-overlay">
          <div className="modal danger">
            <div className="modal-hdr">
              <div className="modal-title" style={{ color: "#f87171" }}>确认下架？</div>
              <button className="modal-close" onClick={() => setDelistTarget(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              下架 <strong style={{ color: "#f87171" }}>{delistTarget.display_name}</strong> 后：策略广场不再展示，<strong style={{ color: "var(--fg)" }}>已有跟单机器人暂停开仓，可正常平仓</strong>。
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setDelistTarget(null)}>取消</button>
              <button className="btn btn-danger" style={{ flex: 1 }} onClick={doDelist}>确认下架</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
