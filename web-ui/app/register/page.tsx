"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const invite = searchParams.get("invite") ?? "";
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      await apiFetch("/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code }) });
      router.push(`/login?activated=1${invite ? `&invite=${invite}` : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="card" style={{ width: 400, position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#00d4aa" }}>signal·saas</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>
            {step === 1 ? "注册账号 · 第 1 步" : "邮箱验证 · 第 2 步"}
          </div>
        </div>
        {invite && (
          <div style={{ background: "rgba(0,212,170,0.1)", border: "1px solid rgba(0,212,170,0.35)", color: "var(--accent)", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>
            好友邀请注册 · 邀请码 <strong style={{ letterSpacing: 2 }}>{invite}</strong>（登录后可在「我的账户」绑定）
          </div>
        )}
        {error && <div className="error-box">{error}</div>}

        {step === 1 ? (
          <form onSubmit={onRegister} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label className="label">邮箱</label>
              <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <label className="label">密码（至少 8 位）</label>
              <input className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <div>
              <label className="label">确认密码</label>
              <input className="input" type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "提交中…" : "获取验证码"}
            </button>
          </form>
        ) : (
          <form onSubmit={onVerify} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ color: "var(--muted)", fontSize: 13 }}>
              验证码已发送至 <strong style={{ color: "var(--fg)" }}>{email}</strong>（5 分钟内有效）。
              开发环境固定验证码：<strong style={{ color: "var(--accent)" }}>123456</strong>
            </div>
            <div>
              <label className="label">6 位验证码</label>
              <input
                className="input"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
              />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "验证中…" : "激活账号"}
            </button>
          </form>
        )}

        <div style={{ marginTop: 20, fontSize: 13, color: "var(--muted)", textAlign: "center" }}>
          已有账号？ <Link href="/login" style={{ color: "var(--accent)" }}>去登录</Link>
        </div>
      </div>
    </main>
  );
}
