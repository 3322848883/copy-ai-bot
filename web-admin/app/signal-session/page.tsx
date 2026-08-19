"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

/** 模式2 信号源 · Gate 登录会话（后台「信号源登录」，★G26 运维看板）。
 *  通过「截图推送 + 输入事件转发」内嵌远程浏览器视图，在页面内直接完成 Gate 登录
 *  （含验证码/滑块），登录态持久化到 user_data_dir 供信号源复用。
 */
type Status = {
  enabled: boolean;
  state: string;          // idle / launching / active / logged_in
  logged_in: boolean;
  trader_count: number;
  message: string;
  url: string;
  has_persisted: boolean;
  source_mode: string;
};

type Leader = {
  leader_id: number | string;
  nick: string;
  roi_30d: number;
  win_rate_all: number;
  max_drawdown: number;
  followers: number;
  is_follow?: boolean;
  is_full?: boolean;
};

const REMOTE_W = 1440;
const REMOTE_H = 900;
// 信号源登录页地址（Gate 改版或换源时改这一处即可）
const SIGNAL_LOGIN_URL = process.env.NEXT_PUBLIC_SIGNAL_LOGIN_URL || "https://www.gate.com/login";

const STATE_META: Record<string, { label: string; cls: string; hint: string }> = {
  idle: { label: "空闲", cls: "ws-offline", hint: "未启动远程浏览器" },
  launching: { label: "启动中", cls: "ws-reconnect", hint: "正在拉起持久化浏览器…" },
  active: { label: "会话中", cls: "ws-reconnect", hint: "远程浏览器运行中，等待完成登录" },
  logged_in: { label: "已登录", cls: "ws-online", hint: "登录态已持久化，信号源可复用" },
};

export default function AdminSignalSessionPage() {
  const router = useRouter();
  const toast = useToast();
  const [status, setStatus] = useState<Status | null>(null);
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [polling, setPolling] = useState(false);
  // 204（无浏览器画面）与加载中区分：避免"正在加载远程画面…"永久转圈
  const [noFeed, setNoFeed] = useState(false);
  const viewRef = useRef<HTMLDivElement>(null);
  const lastMouse = useRef<{ x: number; y: number } | null>(null);
  // 鼠标交互期间暂停截图刷帧，避免画面抖动干扰精确定位（交互结束约 0.8s 后恢复）
  const interactingUntil = useRef(0);
  const PAUSE_AFTER_MS = 800;
  const markInteracting = useCallback(() => {
    interactingUntil.current = Date.now() + PAUSE_AFTER_MS;
  }, []);

  // 搜索带单员
  const [kw, setKw] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<Leader[] | null>(null);
  const [searchMsg, setSearchMsg] = useState("");
  // ★ 搜索带单员 → 设为数据源（进入「信号源审核」流水线）
  const [importingIds, setImportingIds] = useState<Set<string>>(new Set());
  const [importedIds, setImportedIds] = useState<Set<string>>(new Set());

  const loadStatus = useCallback(async () => {
    try {
      const r = await apiFetch<Status>("/admin/v1/signal-session/status", {}, tokenStore.adminAccess);
      setStatus(r);
      setMsg(r.message || "");
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    loadStatus();
  }, [loadStatus, router]);

  // 切回浏览器标签页时自动刷新状态（登录态可能被 worker/其他进程更新）
  useEffect(() => {
    const onFocus = () => loadStatus();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [loadStatus]);

  // 截图轮询：仅当远程浏览器实际拉起（polling）时持续拉取画面
  useEffect(() => {
    if (!polling) return;
    let alive = true;
    const tick = async () => {
      try {
        // 鼠标交互期间暂停刷帧，画面保持稳定便于精确定位
        if (Date.now() < interactingUntil.current) return;
        const r = await fetch(`${API_BASE}/admin/v1/signal-session/screenshot`, {
          headers: { Authorization: `Bearer ${tokenStore.adminAccess}` },
        });
        if (r.status === 204) {
          if (alive) { setImgSrc(null); setNoFeed(true); }
          return;
        }
        if (r.ok) {
          const blob = await r.blob();
          if (alive) { setNoFeed(false); setImgSrc(URL.createObjectURL(blob)); }
        }
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(() => { if (alive) tick(); }, 600);
    return () => { alive = false; clearInterval(id); };
  }, [polling]);

  async function doStart() {
    setMsg("");
    try {
      const r = await apiFetch<Status>("/admin/v1/signal-session/start", { method: "POST" }, tokenStore.adminAccess);
      setStatus(r);
      if (r.state === "idle") {
        // 拉起失败（浏览器崩溃/依赖缺失）：不进入远程视图，避免 204 空转
        setMsg(r.message || "启动失败：远程浏览器未能拉起");
        toast("error", r.message || "启动失败：远程浏览器未能拉起");
        return;
      }
      setNoFeed(false);
      setMsg(r.message || "已启动远程浏览器，请在视图中完成 Gate 登录");
      setPolling(true);
      toast("info", "远程浏览器已启动，请完成登录");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "启动失败");
      toast("error", e instanceof Error ? e.message : "启动失败");
    }
  }

  async function doComplete() {
    try {
      const r = await apiFetch<Status>("/admin/v1/signal-session/complete", { method: "POST" }, tokenStore.adminAccess);
      setStatus(r);
      setMsg(r.message || (r.logged_in ? "登录成功，会话已持久化" : "未检测到有效登录"));
      if (r.logged_in) {
        // ★ 登录成功后保持远程视图开启：管理员还需在 Gate 页面完成「跟单交易员」操作，
        //   完成后点「关闭会话」释放浏览器（否则无法继续跟单操作）
        toast("success", "登录成功，可继续在画面中搜索并跟单交易员");
      } else {
        toast("warn", "尚未检测到有效登录");
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "校验失败");
      toast("error", e instanceof Error ? e.message : "校验失败");
    }
  }

  async function doClose() {
    try {
      await apiFetch("/admin/v1/signal-session/close", { method: "POST" }, tokenStore.adminAccess);
      setPolling(false);
      setImgSrc(null);
      setMsg("会话已关闭（登录态已保留，信号源可复用）");
      toast("success", "会话已关闭，登录态保留");
      await loadStatus();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "关闭失败");
      toast("error", e instanceof Error ? e.message : "关闭失败");
    }
  }

  // 前端鼠标坐标 → 远程 1440x900 坐标
  function toRemote(e: React.MouseEvent): { x: number; y: number } {
    const el = viewRef.current!;
    const rect = el.getBoundingClientRect();
    const scaleX = REMOTE_W / rect.width;
    const scaleY = REMOTE_H / rect.height;
    return { x: Math.round((e.clientX - rect.left) * scaleX), y: Math.round((e.clientY - rect.top) * scaleY) };
  }

  async function sendEvent(evt: Record<string, unknown>) {
    try {
      if (evt.type === "mousemove") lastMouse.current = { x: evt.x as number, y: evt.y as number };
      await apiFetch("/admin/v1/signal-session/event", { method: "POST", body: JSON.stringify(evt) }, tokenStore.adminAccess);
    } catch { /* ignore */ }
  }

  async function doSearch() {
    const keyword = kw.trim();
    if (!keyword) {
      toast("warn", "请输入带单员昵称或 ID");
      return;
    }
    setSearching(true);
    setSearchMsg("");
    try {
      const r = await apiFetch<{ ok: boolean; items: Leader[]; message?: string; source?: string }>(
        `/admin/v1/signal-session/search?keyword=${encodeURIComponent(keyword)}`,
        {},
        tokenStore.adminAccess,
      );
      if (!r.ok) {
        setResults(null);
        setSearchMsg(r.message || "搜索失败");
        toast("warn", r.message || "搜索失败，请先完成 Gate 登录");
        return;
      }
      setResults(r.items || []);
      setSearchMsg(r.items?.length ? `找到 ${r.items.length} 个结果（${r.source === "detail" ? "ID 精确查询" : "昵称模糊匹配"}）` : "未找到匹配的带单员");
      if (!r.items?.length) toast("info", "未找到匹配的带单员");
    } catch (e) {
      setResults(null);
      setSearchMsg(e instanceof Error ? e.message : "搜索失败");
      toast("error", e instanceof Error ? e.message : "搜索失败");
    } finally {
      setSearching(false);
    }
  }

  // ★ 设为数据源：把搜索结果导入「信号源审核」待选池（POST /admin/v1/signals/import）
  async function setAsSource(r: Leader) {
    const id = String(r.leader_id);
    if (importingIds.has(id) || importedIds.has(id)) return;
    setImportingIds((s) => new Set(s).add(id));
    try {
      const res = await apiFetch<{ ok: boolean; message?: string; already_listed?: boolean; collector_ready?: boolean }>(
        "/admin/v1/signals/import",
        { method: "POST", body: JSON.stringify({ exchange: "gate", trader_id: id, name: r.nick || "", followers: 0 }) },
        tokenStore.adminAccess,
      );
      toast(res.ok ? "success" : "warn", res.message || (res.ok ? "已加入待选池，请在「信号源审核」完成上架" : "导入失败"));
      if (res.ok || res.already_listed) setImportedIds((s) => new Set(s).add(id));
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "导入失败");
    } finally {
      setImportingIds((s) => { const n = new Set(s); n.delete(id); return n; });
    }
  }

  const active = status?.state === "active" || status?.state === "logged_in";
  const sm = status ? STATE_META[status.state] || STATE_META.idle : null;

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">SIGNAL SOURCE LOGIN</div>
          <h1 className="page-title">信号源登录<small>模式2 · Gate 持久化会话 · 登录态复用</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-secondary" onClick={loadStatus}>刷新状态</button>
        </div>
      </div>

      {/* 功能未启用 */}
      {status && !status.enabled && (
        <div className="panel" style={{ borderColor: "rgba(239,68,68,0.4)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 18, color: "#f87171" }}>⚠</span>
            <div>
              <div style={{ fontWeight: 600, color: "#f87171" }}>signal_session 功能未启用</div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>
                请在 config 中设置 <code style={{ fontFamily: "var(--font-geist-mono), monospace" }}>signal_session_enabled: true</code> 后重启 API 服务；启用后可在此完成 Gate 登录并搜索带单员。
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 状态总览 KPI */}
      {status?.enabled && (
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-l">会话状态</div>
            <div className="kpi-v" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className={`ws-dot ${sm?.cls || "ws-offline"}`}></span>
              {sm?.label || status.state}
            </div>
            <div className="kpi-s">{sm?.hint || "—"}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">登录状态</div>
            <div className="kpi-v" style={{ color: status.logged_in ? "var(--success)" : "var(--muted)" }}>
              {status.logged_in ? "已登录" : "未登录"}
            </div>
            <div className="kpi-s">{status.has_persisted ? "登录态已落盘" : "无持久化登录态"}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">跟单交易员</div>
            <div className="kpi-v">{status.trader_count}</div>
            <div className="kpi-s">当前跟单对象数</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">登录态持久化</div>
            <div className="kpi-v" style={{ color: status.has_persisted ? "var(--accent)" : "var(--muted)" }}>
              {status.has_persisted ? "已持久化" : "未持久化"}
            </div>
            <div className="kpi-s">user_data_dir 自动落盘</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-l">采集模式</div>
            <div className="kpi-v" style={{ fontSize: 16 }}>{status.source_mode === "follower" ? "模式 2 · 跟单账户" : status.source_mode}</div>
            <div className="kpi-s">source_mode 字段</div>
          </div>
        </div>
      )}

      {/* 操作面板：三步引导 */}
      {status?.enabled && (
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>会话操作</div>
            <span className="panel-sub">start → complete → close · 写操作审计</span>
          </div>

          {/* 步骤引导 */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            {[
              { n: "①", t: "启动浏览器", d: "拉起持久化 Chrome", on: status.state !== "idle" },
              { n: "②", t: "完成登录", d: "校验会话并落盘", on: active },
              { n: "③", t: "复用登录态", d: "信号源 fetch 复用", on: status.logged_in && status.has_persisted },
            ].map((s, i) => (
              <div key={s.n} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", borderRadius: 6, border: "1px solid", borderColor: s.on ? "rgba(239,68,68,0.4)" : "var(--rule)", background: s.on ? "rgba(239,68,68,0.06)" : "transparent" }}>
                  <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 13, color: s.on ? "var(--admin-red)" : "var(--muted)" }}>{s.n}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: s.on ? "var(--fg)" : "var(--muted)" }}>{s.t}</div>
                    <div style={{ fontSize: 10, color: "var(--muted)" }}>{s.d}</div>
                  </div>
                </div>
                {i < 2 && <span style={{ color: "var(--text-tertiary, #64748b)", fontSize: 12 }}>→</span>}
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            {!polling && (
              <button className="btn btn-primary" onClick={doStart}>
                {status.logged_in ? "打开远程浏览器（跟单操作）" : "开始登录"}
              </button>
            )}
            {polling && (
              <>
                <button className="btn btn-primary" onClick={doComplete}>完成登录校验</button>
                <button className="btn btn-secondary" onClick={doClose}>关闭会话（释放浏览器）</button>
              </>
            )}
            <span style={{ color: "var(--muted)", fontSize: 12 }}>
              当前页面：<code style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{status.url || "—"}</code>
            </span>
          </div>
          {!polling && status.logged_in && (
            <div style={{ color: "var(--accent)", fontSize: 12, marginTop: 10 }}>
              ★ 登录态有效但远程浏览器未运行（采集端复用登录态）。如需在 Gate 页面搜索/跟单交易员，
              点击「打开远程浏览器（跟单操作）」。
            </div>
          )}
          {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginTop: 12 }}>{msg}</div>}
        </div>
      )}

      {/* 远程浏览器视图：仅浏览器实际拉起（polling）时显示 */}
      {status?.enabled && polling && (
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>远程浏览器视图</div>
            <span className="panel-sub">截图推送 · 输入事件转发 · 坐标 1440×900</span>
          </div>
          {imgSrc ? (
            <div
              ref={viewRef}
              style={{ position: "relative", width: "100%", border: "1px solid var(--rule)", borderRadius: 8, overflow: "hidden", cursor: "crosshair", aspectRatio: `${REMOTE_W}/${REMOTE_H}`, background: "#0b0e14" }}
              onMouseMove={(e) => { markInteracting(); const p = toRemote(e); sendEvent({ type: "mousemove", x: p.x, y: p.y }); }}
              onMouseDown={(e) => { markInteracting(); }}
              onClick={(e) => { markInteracting(); const p = toRemote(e); sendEvent({ type: "click", x: p.x, y: p.y, button: "left" }); }}
              onWheel={(e) => { markInteracting(); sendEvent({ type: "wheel", deltaX: e.deltaX, deltaY: e.deltaY }); }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imgSrc} alt="远程浏览器" style={{ width: "100%", height: "100%", objectFit: "fill", imageRendering: "auto" }} draggable={false} />
            </div>
          ) : noFeed ? (
            <div style={{ color: "var(--muted)", padding: 40, textAlign: "center" }}>
              远程浏览器暂无画面（可能已被关闭或启动失败）——点「刷新状态」确认，或重新拉起。
            </div>
          ) : (
            <div style={{ color: "var(--muted)", padding: 40, textAlign: "center" }}>正在加载远程画面…</div>
          )}

          {/* 输入工具栏 */}
          <div style={{ display: "flex", gap: 10, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 240 }}
              placeholder="在光标焦点处输入文本（如账号/邮箱）"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { sendEvent({ type: "type", text }); setText(""); } }}
            />
            <button className="btn btn-secondary" onClick={() => { sendEvent({ type: "type", text }); setText(""); }}>输入</button>
            <button className="btn btn-secondary" onClick={() => sendEvent({ type: "press", key: "Enter" })}>回车</button>
            <button className="btn btn-secondary" onClick={() => sendEvent({ type: "press", key: "Tab" })}>Tab</button>
            <button className="btn btn-secondary" onClick={() => sendEvent({ type: "press", key: "Escape" })}>Esc</button>
            <button className="btn btn-secondary" onClick={() => sendEvent({ type: "navigate", url: SIGNAL_LOGIN_URL })}>回登录页</button>
          </div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
            操作方式：先在画面中点击定位光标，再在下方输入框填文本后点「输入」；验证码 / 滑块请直接在画面中用鼠标完成。
          </div>
        </div>
      )}

      {/* 搜索带单员 */}
      {status?.enabled && (
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>搜索带单员</div>
            <span className="panel-sub">/admin/v1/signal-session/search · 搜索后可「设为数据源」进入审核流水线</span>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            <input
              className="input"
              style={{ width: 280 }}
              placeholder="昵称模糊匹配 / 纯数字 ID 精确查询"
              value={kw}
              onChange={(e) => setKw(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }}
            />
            <button className="btn btn-primary" onClick={doSearch} disabled={searching || !kw.trim()}>
              {searching ? "搜索中…" : "搜索"}
            </button>
            {searchMsg && <span style={{ color: "var(--muted)", fontSize: 12 }}>{searchMsg}</span>}
          </div>
          {results && results.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="ftx-table">
                <thead>
                  <tr><th>带单员 ID</th><th>昵称</th><th className="num">30日收益</th><th className="num">总胜率</th><th className="num">最大回撤</th><th className="num">跟单人数</th><th>状态</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={String(r.leader_id)}>
                      <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{r.leader_id}</td>
                      <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{r.nick || "—"}</td>
                      <td className="num" style={{ color: r.roi_30d >= 0 ? "var(--success)" : "#f87171" }}>{r.roi_30d.toFixed(1)}%</td>
                      <td className="num">{r.win_rate_all.toFixed(1)}%</td>
                      <td className="num" style={{ color: r.max_drawdown > 30 ? "#f87171" : undefined }}>{r.max_drawdown.toFixed(1)}%</td>
                      <td className="num">{r.followers.toLocaleString()}</td>
                      <td>
                        {r.is_follow ? <span className="badge badge-info">已跟单</span> : r.is_full ? <span className="badge badge-warn">已满员</span> : <span className="badge badge-muted">可跟单</span>}
                      </td>
                      <td>
                        {importedIds.has(String(r.leader_id)) ? (
                          <span className="badge badge-ok">已导入</span>
                        ) : (
                          <button
                            className="btn btn-secondary"
                            style={{ padding: "4px 10px", fontSize: 12 }}
                            disabled={importingIds.has(String(r.leader_id))}
                            onClick={() => setAsSource(r)}
                          >
                            {importingIds.has(String(r.leader_id)) ? "导入中…" : "设为数据源"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
