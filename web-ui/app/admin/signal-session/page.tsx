"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

/** 模式2 信号源·Gate 登录会话（后台管理「登录 Gate」）。
 *  通过「截图推送 + 输入事件转发」内嵌一个远程浏览器视图：
 *  在页面里直接操作服务器端浏览器完成 Gate 登录（含验证码/滑块），
 *  登录态持久化到 user_data_dir，供 fetch_follower_positions 复用。
 */
type Status = {
  enabled: boolean;
  state: string;          // idle/launching/active/logged_in
  logged_in: boolean;
  trader_count: number;
  message: string;
  url: string;
  has_persisted: boolean;
  source_mode: string;
};

const REMOTE_W = 1440;
const REMOTE_H = 900;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export default function AdminSignalSessionPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [polling, setPolling] = useState(false);
  const viewRef = useRef<HTMLDivElement>(null);
  const lastMouse = useRef<{ x: number; y: number } | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const r = await apiFetch<Status>("/admin/v1/signal-session/status", {}, tokenStore.adminAccess);
      setStatus(r);
      setMsg(r.message || "");
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    loadStatus();
  }, [loadStatus, router]);

  // 截图轮询：仅当会话非 idle 时持续拉取远程画面
  useEffect(() => {
    if (!polling) return;
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/admin/v1/signal-session/screenshot`, {
          headers: { Authorization: `Bearer ${tokenStore.adminAccess}` },
        });
        if (r.ok) {
          const blob = await r.blob();
          if (alive) setImgSrc(URL.createObjectURL(blob));
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
      setMsg(r.message || "已启动远程浏览器，请在弹出的视图中完成 Gate 登录");
      setPolling(true);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "启动失败");
    }
  }

  async function doComplete() {
    try {
      const r = await apiFetch<Status>("/admin/v1/signal-session/complete", { method: "POST" }, tokenStore.adminAccess);
      setStatus(r);
      setMsg(r.message || (r.logged_in ? "登录成功，会话已持久化" : "未检测到有效登录"));
      if (r.logged_in) setPolling(false);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "校验失败");
    }
  }

  async function doClose() {
    try {
      await apiFetch("/admin/v1/signal-session/close", { method: "POST" }, tokenStore.adminAccess);
      setPolling(false);
      setImgSrc(null);
      setMsg("会话已关闭（登录态已保留，信号源可复用）");
      await loadStatus();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "关闭失败");
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
      if (evt.type === "mousemove") {
        lastMouse.current = { x: evt.x as number, y: evt.y as number };
      }
      await apiFetch("/admin/v1/signal-session/event", {
        method: "POST",
        body: JSON.stringify(evt),
      }, tokenStore.adminAccess);
    } catch { /* ignore */ }
  }

  const active = status?.state === "active" || status?.state === "logged_in";

  return (
    <div style={{ maxWidth: 980 }}>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>模式2 信号源 · Gate 登录</div>
      <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>
        source_mode = {status?.source_mode ?? "follower"}（监控自己的跟单账户镜像持仓）。需在此完成 Gate 登录，登录态持久化供信号源复用。
      </div>
      {!status?.enabled && (
        <div className="card" style={{ padding: 24, color: "var(--danger)" }}>
          signal_session 功能未启用。请在 config.yaml 设置 <code>signal_session_enabled: true</code>。
        </div>
      )}

      {status?.enabled && (
        <div className="card" style={{ padding: 24, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 700 }}>会话状态</div>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>state / 登录 / 跟单数</div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="tag">{status.state}</span>
              <span className="tag" style={{ color: status.logged_in ? "var(--success)" : "var(--muted)" }}>
                {status.logged_in ? "已登录" : "未登录"}
              </span>
              <span className="tag">跟单 {status.trader_count}</span>
              {status.has_persisted && <span className="tag" style={{ color: "var(--accent)" }}>已持久化</span>}
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
              {!active && <button className="btn btn-primary" onClick={doStart}>开始登录</button>}
              {active && (
                <>
                  <button className="btn btn-primary" onClick={doComplete}>完成登录</button>
                  <button className="btn" onClick={doClose} style={{ border: "1px solid var(--rule)" }}>关闭会话</button>
                </>
              )}
            </div>
          </div>
          {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginTop: 12 }}>{msg}</div>}
          {status.url && <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>当前页面：{status.url}</div>}
        </div>
      )}

      {active && (
        <div className="card" style={{ padding: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>远程浏览器视图（在此完成登录 / 验证码 / 滑块）</div>
          {imgSrc ? (
            <div
              ref={viewRef}
              style={{ position: "relative", width: "100%", border: "1px solid var(--rule)", borderRadius: 8, overflow: "hidden", cursor: "crosshair", aspectRatio: `${REMOTE_W}/${REMOTE_H}`, background: "#0b0e14" }}
              onMouseMove={(e) => { const p = toRemote(e); sendEvent({ type: "mousemove", x: p.x, y: p.y }); }}
              onClick={(e) => { const p = toRemote(e); sendEvent({ type: "click", x: p.x, y: p.y, button: "left" }); }}
              onWheel={(e) => sendEvent({ type: "wheel", deltaX: e.deltaX, deltaY: e.deltaY })}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imgSrc} alt="远程浏览器" style={{ width: "100%", height: "100%", objectFit: "fill", imageRendering: "auto" }} draggable={false} />
            </div>
          ) : (
            <div style={{ color: "var(--muted)", padding: 40, textAlign: "center" }}>正在加载远程画面…</div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 12, alignItems: "center" }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="在光标焦点处输入文本（如账号/邮箱）"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { sendEvent({ type: "type", text }); setText(""); } }}
            />
            <button className="btn" style={{ border: "1px solid var(--rule)" }} onClick={() => { sendEvent({ type: "type", text }); setText(""); }}>输入</button>
            <button className="btn" style={{ border: "1px solid var(--rule)" }} onClick={() => sendEvent({ type: "press", key: "Enter" })}>回车</button>
            <button className="btn" style={{ border: "1px solid var(--rule)" }} onClick={() => sendEvent({ type: "press", key: "Tab" })}>Tab</button>
          </div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
            操作方式：先在页面内点击定位光标，在下方输入框填文本后点「输入」；验证码/滑块请直接在画面中用鼠标完成。
          </div>
        </div>
      )}
    </div>
  );
}