"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type ApiKey = { id: number; exchange: string };

const EXCHANGE_LABEL: Record<string, string> = { gate: "Gate", binance: "Binance", okx: "OKX", bybit: "Bybit", bitget: "Bitget" };

/** T1.8 个人中心：账户概览 + 选所 + API 绑定（含 G27 交易所邀请码）。 */
export default function AccountPage() {
  const router = useRouter();
  const [exchange, setExchange] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  // ★ API 密钥列表 + 好友邀请码绑定
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [friendCode, setFriendCode] = useState("");
  const [friendMsg, setFriendMsg] = useState("");
  const [unbinding, setUnbinding] = useState<string | null>(null);
  // ★ 修改密码
  const [pwdForm, setPwdForm] = useState({ old_password: "", new_password: "", confirm: "" });
  const [pwdMsg, setPwdMsg] = useState("");
  const [pwdErr, setPwdErr] = useState("");

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
    loadKeys();
  }, [loadKeys, router]);

  async function onBindFriendInvite(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setFriendMsg(""); setLoading(true);
    try {
      await apiFetch("/v1/identity/bind-invite", { method: "POST", body: JSON.stringify({ code: friendCode }) }, tokenStore.access);
      setFriendMsg("好友邀请码绑定成功");
      setFriendCode("");
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
      const res = await apiFetch<{ exchange: string }>("/v1/identity/choose-exchange", { method: "POST", body: JSON.stringify({ exchange }) }, tokenStore.access);
      setMsg(`所属交易所已设为 ${res.exchange}`);
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
      const res = await apiFetch<{ message: string }>("/v1/identity/bind-exchange-invite", { method: "POST", body: JSON.stringify({ exchange, code: inviteCode }) }, tokenStore.access);
      setMsg(res.message);
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
      const res = await apiFetch<{ message: string }>("/v1/apikeys", { method: "POST", body: JSON.stringify({ exchange, api_key: apiKey, api_secret: apiSecret }) }, tokenStore.access);
      setMsg(res.message);
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

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 820, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>个人中心</div>
            <div style={{ color: "var(--muted)", fontSize: 13 }}>账户概览 · 选所 · 交易所邀请码 · API 管理</div>
          </div>
          <button className="btn btn-secondary" onClick={onLogout}>退出登录</button>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {err && <div className="error-box">{err}</div>}

        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>所属交易所</div>
          <form onSubmit={onChooseExchange} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label className="label">选择交易所</label>
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
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>★ 交易所邀请码（G27，注册必填）</div>
          <form onSubmit={onBindExchangeInvite} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label className="label">邀请码</label>
              <input className="input" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} placeholder="如 8F3K2A" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading || !inviteCode}>绑定</button>
          </form>
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>好友邀请码绑定</div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>
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

        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 4 }}>API 密钥管理</div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>
            实时校验连通性与权限；<span style={{ color: "#f87171" }}>禁止绑定带提现权限的 Key（合规红线）</span>
          </div>

          {/* ★ 已绑定 API 列表 + 解绑（GET/DELETE /v1/apikeys） */}
          <div style={{ marginBottom: 16 }}>
            {apiKeys.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: 12, padding: "10px 14px", background: "var(--surface)", border: "1px dashed var(--rule)", borderRadius: 6 }}>
                尚未绑定任何交易所 API Key
              </div>
            ) : (
              apiKeys.map((k) => (
                <div key={k.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", border: "1px solid var(--rule)", borderRadius: 6, marginBottom: 8 }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{EXCHANGE_LABEL[k.exchange] || k.exchange}</span>
                    <span style={{ color: "var(--muted)", fontSize: 12, marginLeft: 8 }}>已绑定 · 权限已校验</span>
                  </div>
                  <button
                    className="btn btn-secondary"
                    style={{ padding: "4px 12px", fontSize: 12, color: "var(--danger)", borderColor: "rgba(239,68,68,0.4)" }}
                    disabled={unbinding === k.exchange}
                    onClick={() => onUnbindApi(k.exchange)}
                  >
                    {unbinding === k.exchange ? "解绑中…" : "解绑"}
                  </button>
                </div>
              ))
            )}
          </div>

          <form onSubmit={onBindApi} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label className="label">API Key</label>
              <input className="input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="粘贴 API Key" />
            </div>
            <div>
              <label className="label">API Secret（AES-256-GCM 加密存储）</label>
              <input className="input" type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="粘贴 Secret" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading || !apiKey || !apiSecret}>
              校验并绑定
            </button>
          </form>
        </div>

        {/* ★ 修改密码（POST /v1/auth/change-password，成功后吊销旧 refresh） */}
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>修改密码</div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>修改后所有设备需重新登录</div>
          {pwdMsg && <div style={{ color: "var(--success)", fontSize: 13, marginBottom: 10 }}>{pwdMsg}</div>}
          {pwdErr && <div className="error-box" style={{ marginBottom: 10 }}>{pwdErr}</div>}
          <form onSubmit={onChangePassword} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label className="label">原密码</label>
              <input className="input" type="password" value={pwdForm.old_password} onChange={(e) => setPwdForm({ ...pwdForm, old_password: e.target.value })} placeholder="输入原密码" />
            </div>
            <div>
              <label className="label">新密码</label>
              <input className="input" type="password" value={pwdForm.new_password} onChange={(e) => setPwdForm({ ...pwdForm, new_password: e.target.value })} placeholder="至少 8 位" />
            </div>
            <div>
              <label className="label">确认新密码</label>
              <input className="input" type="password" value={pwdForm.confirm} onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })} placeholder="再次输入新密码" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading || !pwdForm.old_password || !pwdForm.new_password}>
              确认修改
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
