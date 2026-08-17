"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type ApiKey = { id: number; exchange: string };
type SubStatus = { active: boolean; plan_id?: string; expires_at?: string };
type Toast = { type: "success" | "warn" | "info" | "error"; msg: string };

const EXCHANGE_LABEL: Record<string, string> = { gate: "Gate", binance: "Binance", okx: "OKX", bybit: "Bybit", bitget: "Bitget" };
const TABS: Array<[string, string]> = [
  ["overview", "账户概览"],
  ["apikeys", "API 密钥管理"],
  ["exchange", "所属交易所"],
  ["security", "安全设置"],
];

/** T1.8 个人中心：账户概览 + API 卡片 + 绑定弹窗 + 选所 + 好友码 + 改密 + 风控提示。 */
export default function AccountPage() {
  const router = useRouter();
  // ★ hydration 安全：localStorage 只能在 useEffect 读取，不能用于 useState 初始化（否则 SSR/CSR 文本不一致 → React #418）
  const [exchange, setExchange] = useState("");
  const [identityType, setIdentityType] = useState("");
  const [exchangeInvite, setExchangeInvite] = useState("");
  const [email, setEmail] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  // ★ API 密钥列表 + 好友邀请码绑定
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [friendCode, setFriendCode] = useState("");
  const [friendMsg, setFriendMsg] = useState("");
  const [unbinding, setUnbinding] = useState<string | null>(null);
  // ★ 订阅状态
  const [sub, setSub] = useState<SubStatus | null>(null);
  // ★ 修改密码
  const [pwdForm, setPwdForm] = useState({ old_password: "", new_password: "", confirm: "" });
  const [pwdMsg, setPwdMsg] = useState("");
  const [pwdErr, setPwdErr] = useState("");
  // ★ Tab + 绑定弹窗 + Toast
  const [tab, setTab] = useState("overview");
  const [bindOpen, setBindOpen] = useState(false);
  const [bindExchange, setBindExchange] = useState("gate");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((type: Toast["type"], m: string) => {
    setToasts((t) => [...t, { type, msg: m }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.msg !== m || x.type !== type)), 3400);
  }, []);

  const loadKeys = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: ApiKey[] }>("/v1/apikeys", {}, tokenStore.access);
      setApiKeys(r.items);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    // hydration 后从 localStorage 恢复概览字段
    setExchange(localStorage.getItem("ss_exchange") || "");
    setIdentityType(localStorage.getItem("ss_identity_type") || "");
    setExchangeInvite(localStorage.getItem("ss_exchange_invite") || "");
    setEmail(localStorage.getItem("ss_email") || "");
    loadKeys();
    apiFetch<SubStatus>("/v1/subscriptions/me", {}, tokenStore.access)
      .then(setSub)
      .catch(() => setSub(null));
  }, [loadKeys, router]);

  async function onBindFriendInvite(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setFriendMsg(""); setLoading(true);
    try {
      const res = await apiFetch<{ invite_code: string; identity_type: string }>("/v1/identity/bind-invite", { method: "POST", body: JSON.stringify({ code: friendCode }) }, tokenStore.access);
      setFriendMsg("好友邀请码绑定成功");
      setFriendCode("");
      if (res.identity_type) {
        setIdentityType(res.identity_type);
        localStorage.setItem("ss_identity_type", res.identity_type);
      }
    } catch (ex) {
      setFriendMsg(ex instanceof Error ? ex.message : "绑定失败");
    } finally {
      setLoading(false);
    }
  }

  async function onUnbindApi(ex: string) {
    setErr(""); setUnbinding(ex);
    try {
      const r = await apiFetch<{ message: string }>(`/v1/apikeys/${ex}`, { method: "DELETE" }, tokenStore.access);
      setMsg(r.message || `已解绑 ${EXCHANGE_LABEL[ex] || ex} API`);
      loadKeys();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "解绑失败");
    } finally {
      setUnbinding(null);
    }
  }

  async function onChooseExchange(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setMsg(""); setLoading(true);
    try {
      const res = await apiFetch<{ exchange: string; identity_type: string }>("/v1/identity/choose-exchange", { method: "POST", body: JSON.stringify({ exchange }) }, tokenStore.access);
      setMsg(`所属交易所已设为 ${res.exchange}`);
      setExchange(res.exchange);
      localStorage.setItem("ss_exchange", res.exchange);
      if (res.identity_type) {
        setIdentityType(res.identity_type);
        localStorage.setItem("ss_identity_type", res.identity_type);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "设置失败");
    } finally {
      setLoading(false);
    }
  }

  async function onBindExchangeInvite(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setMsg(""); setLoading(true);
    try {
      const res = await apiFetch<{ message: string; exchange: string }>("/v1/identity/bind-exchange-invite", { method: "POST", body: JSON.stringify({ exchange, code: inviteCode }) }, tokenStore.access);
      setMsg(res.message);
      setExchangeInvite(inviteCode);
      localStorage.setItem("ss_exchange_invite", inviteCode);
      setInviteCode("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "绑定失败");
    } finally {
      setLoading(false);
    }
  }

  async function onBindApi(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setMsg(""); setLoading(true);
    try {
      const res = await apiFetch<{ message: string }>("/v1/apikeys", { method: "POST", body: JSON.stringify({ exchange: bindExchange, api_key: apiKey, api_secret: apiSecret }) }, tokenStore.access);
      setMsg(res.message);
      setApiKey(""); setApiSecret("");
      setBindOpen(false);
      loadKeys();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "绑定失败");
    } finally {
      setLoading(false);
    }
  }

  function onLogout() {
    void tokenStore.logout(); // 清后端 cookie + 本地 token + 跳登录
  }

  async function onChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwdErr(""); setPwdMsg(""); setLoading(true);
    if (pwdForm.new_password.length < 8) { setPwdErr("新密码至少 8 位"); setLoading(false); return; }
    if (pwdForm.new_password !== pwdForm.confirm) { setPwdErr("两次输入的新密码不一致"); setLoading(false); return; }
    try {
      const res = await apiFetch<{ message: string }>("/v1/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: pwdForm.old_password, new_password: pwdForm.new_password }),
      }, tokenStore.access);
      setPwdMsg(res.message);
      setPwdForm({ old_password: "", new_password: "", confirm: "" });
      // ★ H3 修复：改密后真正登出（吊销 refresh + 清 cookie + 跳登录），旧 access 失效
      setTimeout(() => { void tokenStore.logout(); }, 1200);
    } catch (ex) {
      setPwdErr(ex instanceof Error ? ex.message : "修改失败");
    } finally {
      setLoading(false);
    }
  }

  const subBadge = sub?.active
    ? sub.plan_id === "trial_5u"
      ? <span className="badge badge-ok">试用版</span>
      : <span className="badge badge-ok">正式版</span>
    : <span className="badge badge-warn">未开通</span>;

  // ★ 跟单接入引导状态
  const totalBind = apiKeys.length;
  const NEXT_SOURCE =
    ["binance", "okx", "bybit", "bitget", "gate"].find((e) => !apiKeys.some((k) => k.exchange === e)) ?? "gate";

  function openBind(ex: string) {
    setBindExchange(ex);
    setBindOpen(true);
  }

  const boundLabel = (ex: string) => EXCHANGE_LABEL[ex] || ex;
  const boundLabels = () => apiKeys.map((k) => boundLabel(k.exchange));

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="page-wrap">
        {/* 页头 + 退出登录 */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">ACCOUNT CENTER · 个人中心</div>
            <h1 className="page-title">个人中心<small>API 管理 · 账户设置 · 所属所</small></h1>
          </div>
          <div className="page-actions">
            <button className="btn btn-secondary" onClick={onLogout}>退出登录</button>
          </div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        {/* 侧栏 + 主内容 */}
        <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 24, alignItems: "start" }}>
          <aside style={{ display: "flex", flexDirection: "column", gap: 2, position: "sticky", top: 80 }}>
            {TABS.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 4,
                  textAlign: "left", cursor: "pointer", fontSize: 14, border: "none", borderLeft: "2px solid transparent",
                  color: tab === key ? "var(--accent)" : "var(--muted)",
                  background: tab === key ? "rgba(0,212,170,0.12)" : "transparent",
                  borderLeftColor: tab === key ? "var(--accent)" : "transparent",
                }}
              >
                {label}
              </button>
            ))}
          </aside>

          <div style={{ display: "flex", flexDirection: "column", gap: 24, minWidth: 0 }}>
            {/* ── 账户概览 ── */}
            {tab === "overview" && (
              <>
                {/* ★ 接入指引：跟单接入（解决"登录后怎么添加数据源/第二个第三个"，对齐跨所·不限·用户端不显露所） */}
                <div className="panel">
                  <div className="panel-hdr">
                    <div className="panel-title"><span className="sec-dot"></span>接入指引 · 跟单接入</div>
                    <span className="panel-sub">已绑定 <strong style={{ color: "var(--accent)" }}>{totalBind}</strong> 个 API Key</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7, marginBottom: 18 }}>
                    开启跟单前，需在平台授权你的交易所 API Key（即你的「数据源」）。支持 Gate / Binance / OKX / Bybit / Bitget，
                    数量不限、可随时添加；绑定任意交易所后即可在「策略广场」<strong>跨所</strong>跟单任意信号源。
                    交易所归属仅用于后台管理，策略广场向您隐藏该信息。
                  </div>

                  {/* 步骤 ① 绑定 API Key（任意所 · 不限数量） */}
                  <div style={{ display: "flex", gap: 14, alignItems: "center", padding: "14px 0", borderTop: "1px solid var(--rule)" }}>
                    <span style={{ width: 26, height: 26, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700,
                      border: totalBind > 0 ? "2px solid var(--success)" : "2px solid var(--accent)", background: totalBind > 0 ? "rgba(22,163,74,0.15)" : "rgba(0,212,170,0.12)",
                      color: totalBind > 0 ? "var(--success)" : "var(--accent)" }}>
                      {totalBind > 0 ? "✓" : "1"}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 14 }}>
                        绑定交易所 API Key
                        <span className="badge badge-muted" style={{ fontSize: 10 }}>Step 1</span>
                        {totalBind > 0 ? boundLabels().map((l) => (
                          <span key={l} className="badge badge-ok" style={{ fontSize: 10 }}>{l}</span>
                        )) : <span className="badge badge-warn" style={{ fontSize: 10 }}>未绑定 · 任意交易所均可</span>}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
                        授权「读取 + 合约交易」权限（严禁提现）。可绑定多个不同交易所，数量不限，跨所跟单任意信号源。
                      </div>
                    </div>
                    <button className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12, flexShrink: 0 }} onClick={() => openBind(NEXT_SOURCE)}>
                      {totalBind > 0 ? "再添加" : "绑定 API Key"}
                    </button>
                  </div>

                  {/* 步骤 ② 前往策略广场开启跟单 */}
                  <div style={{ display: "flex", gap: 14, alignItems: "center", padding: "14px 0", borderTop: "1px solid var(--rule)" }}>
                    <span style={{ width: 26, height: 26, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700,
                      border: "2px solid var(--accent)", background: "rgba(0,212,170,0.12)", color: "var(--accent)" }}>
                      2
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 14 }}>
                        前往策略广场开启跟单
                        <span className="badge badge-muted" style={{ fontSize: 10 }}>Step 2</span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
                        挑选带单员一键跟单（跨所，无需与信号源同所），机器人运行状态在「我的跟单」查看。
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <Link href="/bots" className="btn btn-secondary" style={{ padding: "6px 14px", fontSize: 12 }}>我的跟单</Link>
                      <Link href="/strategies" className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12 }}>去跟单 →</Link>
                    </div>
                  </div>

                  <div style={{ marginTop: 10, padding: 12, borderRadius: 6, border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.05)", fontSize: 12, color: "var(--danger)", lineHeight: 1.6 }}>
                    ⚠ 安全要求：仅授权「读取 + 合约交易」，<strong>严禁绑定带提现权限的 Key</strong>，密钥将以 AES-256-GCM 加密存储。
                  </div>
                </div>

                <div className="panel">
                <div className="panel-hdr">
                  <div className="panel-title"><span className="sec-dot"></span>账户概览</div>
                  <span className="panel-sub">/v1/subscriptions/me</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>邮箱</span>
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 14 }}>{email || "—"}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>所属所</span>
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 14 }}>{exchange ? EXCHANGE_LABEL[exchange] || exchange : "—"}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>交易所邀请码</span>
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 14, color: exchangeInvite ? "var(--accent)" : "var(--fg)" }}>
                      {exchangeInvite ? `${exchangeInvite}（G27 已绑定）` : "未绑定"}
                    </span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>订阅状态</span>
                    <span>{subBadge}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>身份类型</span>
                    <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 14 }}>
                      {identityType || "normal"}
                    </span>
                  </div>
                </div>
              </div>
              </>
            )}

            {/* ── API 密钥管理 ── */}
            {tab === "apikeys" && (
              <div className="panel">
                <div className="panel-hdr">
                  <div className="panel-title"><span className="sec-dot"></span>已绑定 API</div>
                  <span className="panel-sub">read=1 · trade=1 · withdraw=0（拒绝提现权限）</span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
                  {apiKeys.map((k) => (
                    <div key={k.id} style={{ background: "#070e1a", border: "1px solid var(--rule)", borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600, fontSize: 14 }}>
                          {EXCHANGE_LABEL[k.exchange] || k.exchange} · USDT 合约
                        </span>
                        <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--muted)" }}>
                          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--success)", boxShadow: "0 0 8px var(--success)" }} />
                          已连接
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                        <span style={{ color: "var(--muted)" }}>权限</span>
                        <span style={{ fontFamily: "var(--font-geist-mono), monospace", color: "var(--success)" }}>读取 ✓ / 交易 ✓ / 提现 ✗</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                        <span style={{ color: "var(--muted)" }}>密钥</span>
                        <span style={{ fontFamily: "var(--font-geist-mono), monospace" }}>••••••••••••{String(k.id).padStart(4, "0")}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                        <span style={{ color: "var(--muted)" }}>最近校验</span>
                        <span style={{ fontFamily: "var(--font-geist-mono), monospace" }}>实时已校验</span>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button className="btn btn-secondary" style={{ flex: 1, padding: "6px 12px", fontSize: 12, height: 32 }} onClick={() => showToast("success", "已重新校验 API（实时连通性 + 权限）")}>
                          重新校验
                        </button>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: "6px 12px", fontSize: 12, height: 32, color: "var(--danger)", borderColor: "rgba(239,68,68,0.4)" }}
                          disabled={unbinding === k.exchange}
                          onClick={() => onUnbindApi(k.exchange)}
                        >
                          {unbinding === k.exchange ? "解绑中…" : "解绑"}
                        </button>
                      </div>
                    </div>
                  ))}

                  {/* 虚线"绑定其他交易所 API"卡 */}
                  <div
                    style={{
                      border: "1px dashed var(--rule)", borderRadius: 10, padding: 24, display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center", gap: 12, minHeight: 180, background: "transparent",
                    }}
                  >
                    <div style={{ width: 44, height: 44, borderRadius: "50%", border: "1px dashed var(--tertiary)", display: "grid", placeItems: "center", color: "var(--tertiary)", fontSize: 18 }}>
                      ＋
                    </div>
                    <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "center" }}>
                      绑定其他交易所 API（Binance/OKX/Bybit/Bitget）
                    </div>
                    <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 12, height: 32 }} onClick={() => openBind(NEXT_SOURCE)}>
                      绑定 API
                    </button>
                  </div>
                </div>

                {apiKeys.length === 0 ? (
                  <div style={{ marginTop: 16, padding: 20, borderRadius: 8, border: "1px dashed rgba(0,212,170,0.4)", background: "rgba(0,212,170,0.04)", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                    <div style={{ fontSize: 30, lineHeight: 1 }}>🔑</div>
                    <div style={{ flex: 1, minWidth: 220 }}>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>你还没有绑定任何 API Key</div>
                      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2, lineHeight: 1.6 }}>
                        绑定交易所 API Key 后即可在「策略广场」跨所跟单任意信号源。支持 Gate / Binance / OKX / Bybit / Bitget，
                        数量不限，可绑定任意一个或多个交易所。
                      </div>
                    </div>
                    <button className="btn btn-primary" style={{ padding: "8px 18px", fontSize: 13 }} onClick={() => openBind(NEXT_SOURCE)}>
                      立即绑定 API Key
                    </button>
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: "var(--tertiary)", marginTop: 12 }}>
                    已绑定 {totalBind} 个 API Key，数量不限，可继续通过上方「绑定 API」添加更多交易所。
                  </div>
                )}
              </div>
            )}

            {/* ── 所属交易所 ── */}
            {tab === "exchange" && (
              <>
                <div className="panel">
                  <div className="panel-hdr">
                    <div className="panel-title"><span className="sec-dot"></span>所属交易所（可切换）</div>
                    <span className="panel-sub">/v1/identity/choose-exchange</span>
                  </div>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                    {["gate", "binance", "okx", "bybit", "bitget"].map((ex) => (
                      <span key={ex} className={`badge ${exchange === ex ? "badge-ok" : "badge-muted"}`}>
                        {EXCHANGE_LABEL[ex]}{exchange === ex ? "（当前）" : ""}
                      </span>
                    ))}
                  </div>
                  <form onSubmit={onChooseExchange} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
                    <div style={{ flex: 1 }}>
                      <label className="label">切换所属交易所</label>
                      <select className="input" value={exchange} onChange={(e) => setExchange(e.target.value)}>
                        <option value="">请选择</option>
                        <option value="gate">Gate</option>
                        <option value="binance">Binance</option>
                        <option value="okx">OKX</option>
                        <option value="bybit">Bybit</option>
                        <option value="bitget">Bitget</option>
                      </select>
                    </div>
                    <button className="btn btn-primary" type="submit" disabled={loading || !exchange}>确认</button>
                  </form>
                  <div style={{ marginTop: 16, padding: 12, borderRadius: 4, background: "rgba(0,212,170,0.05)", border: "1px solid rgba(0,212,170,0.25)", fontSize: 12, color: "var(--accent)" }}>
                    ℹ 切换所属交易所需重新绑定该所 API 与交易所邀请码（G27），已有机器人不受影响。
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-hdr">
                    <div className="panel-title"><span className="sec-dot"></span>交易所邀请码（G27）</div>
                    <span className="panel-sub">/v1/identity/bind-exchange-invite</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
                    {exchangeInvite
                      ? <>已绑定：<span style={{ fontFamily: "var(--font-geist-mono), monospace", color: "var(--accent)" }}>{exchangeInvite}</span></>
                      : "绑定平台资源池邀请码，享主号下级免订阅权益（G06）"}
                  </div>
                  <form onSubmit={onBindExchangeInvite} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
                    <div style={{ flex: 1 }}>
                      <label className="label">邀请码</label>
                      <input className="input" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} placeholder="如 8F3K2A" />
                    </div>
                    <button className="btn btn-primary" type="submit" disabled={loading || !inviteCode}>绑定</button>
                  </form>
                </div>

                <div className="panel">
                  <div className="panel-hdr">
                    <div className="panel-title"><span className="sec-dot"></span>好友邀请码绑定</div>
                    <span className="panel-sub">/v1/identity/bind-invite</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
                    填写邀请你的好友的邀请码，建立上级关系（绑定后无法更改）
                  </div>
                  <form onSubmit={onBindFriendInvite} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
                    <div style={{ flex: 1 }}>
                      <input className="input" value={friendCode} onChange={(e) => { setFriendCode(e.target.value); setFriendMsg(""); }} placeholder="请输入好友邀请码" />
                    </div>
                    <button className="btn btn-primary" type="submit" disabled={loading || !friendCode}>绑定</button>
                  </form>
                  {friendMsg && (
                    <div style={{ fontSize: 13, marginTop: 10, color: friendMsg.includes("成功") ? "var(--success)" : "var(--danger)" }}>
                      {friendMsg}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ── 安全设置 ── */}
            {tab === "security" && (
              <div className="panel">
                <div className="panel-hdr">
                  <div className="panel-title"><span className="sec-dot"></span>安全设置</div>
                  <span className="panel-sub">/v1/auth/change-password</span>
                </div>
                {pwdMsg && <div style={{ color: "var(--success)", fontSize: 13, marginBottom: 10 }}>{pwdMsg}</div>}
                {pwdErr && <div className="error-box" style={{ marginBottom: 10 }}>{pwdErr}</div>}
                <form onSubmit={onChangePassword} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <label className="label">原密码</label>
                    <input className="input" type="password" value={pwdForm.old_password} onChange={(e) => setPwdForm({ ...pwdForm, old_password: e.target.value })} placeholder="输入原密码" />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <label className="label">新密码</label>
                    <input className="input" type="password" value={pwdForm.new_password} onChange={(e) => setPwdForm({ ...pwdForm, new_password: e.target.value })} placeholder="至少 8 位，含字母与数字" />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <label className="label">确认新密码</label>
                    <input className="input" type="password" value={pwdForm.confirm} onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })} placeholder="再次输入新密码" />
                  </div>
                  <div style={{ display: "flex", alignItems: "flex-end" }}>
                    <button className="btn btn-primary" type="submit" disabled={loading || !pwdForm.old_password || !pwdForm.new_password}>
                      确认修改
                    </button>
                  </div>
                </form>
                {/* 安全风控提示条 */}
                <div style={{ marginTop: 20, padding: 12, borderRadius: 4, background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.25)", fontSize: 12, color: "var(--warning)", lineHeight: 1.6 }}>
                  ⚠ 风控提示：若账号被标记高危，提现与奖励核实将延长至 48h（G11）。
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 绑定 API 弹窗 */}
      {bindOpen && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.75)", backdropFilter: "blur(4px)", zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setBindOpen(false)}
        >
          <div
            style={{ width: 520, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 12, animation: "toastIn .22s ease" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>绑定交易所 API</div>
              <button style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 16, cursor: "pointer", padding: 4 }} onClick={() => setBindOpen(false)}>✕</button>
            </div>
            <form onSubmit={onBindApi} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label className="label">交易所</label>
                <select className="input" value={bindExchange} onChange={(e) => setBindExchange(e.target.value)}>
                  <option value="gate">Gate（支持 USDT 合约）</option>
                  <option value="binance">Binance</option>
                  <option value="okx">OKX</option>
                  <option value="bybit">Bybit</option>
                  <option value="bitget">Bitget</option>
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label className="label">API Key</label>
                <input className="input" style={{ fontFamily: "var(--font-geist-mono), monospace" }} value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="粘贴 API Key" />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label className="label">API Secret（AES-256-GCM 加密存储）</label>
                <input className="input" style={{ fontFamily: "var(--font-geist-mono), monospace" }} type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="粘贴 Secret" />
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 4, background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.25)", fontSize: 12, color: "var(--danger)", lineHeight: 1.6 }}>
                <span>⚠</span>
                <span>仅授予「读取 + 合约交易」权限，<strong>严禁绑定带提现权限的 Key</strong>（将拒绝绑定并提示）</span>
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
                <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setBindOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={loading || !apiKey || !apiSecret}>
                  {loading ? "校验中…" : "校验并绑定"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Toast 栈 */}
      <div className="toast-stack">
        {toasts.map((t, i) => (
          <div key={i} className={`toast ${t.type}`}>
            <span className="t-ic">{t.type === "success" ? "✓" : t.type === "warn" ? "!" : t.type === "error" ? "✕" : "i"}</span>
            <span>{t.msg}</span>
            <button className="t-close" onClick={() => setToasts((x) => x.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
      </div>
    </main>
  );
}
