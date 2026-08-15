"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { apiFetch, tokenStore } from "@/lib/api";
import RiskDisclosureModal from "@/components/RiskDisclosureModal";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [riskOpen, setRiskOpen] = useState(false);

  /** ★ M3 修复：回跳受保护页面（middleware 的 ?next= 参数，同源校验）。 */
  function redirectAfterLogin() {
    const next = searchParams.get("next");
    if (next && next.startsWith("/") && !next.startsWith("//") && !next.includes(":")) {
      router.push(next);
      return;
    }
    router.push("/account");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string; refresh_token?: string; risk_disclosure_accepted?: boolean }>(
        "/v1/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) }
      );
      tokenStore.set(res);
      if (res.risk_disclosure_accepted === false && !tokenStore.riskAccepted) {
        // ★ T1.9：首次登录强制风险揭示
        setRiskOpen(true);
        return;
      }
      redirectAfterLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function onRiskConfirm() {
    try {
      await apiFetch("/v1/auth/accept-risk-disclosure", { method: "POST" }, tokenStore.access);
      tokenStore.setRiskAccepted(true);
      setRiskOpen(false);
      redirectAfterLogin();
    } catch {
      redirectAfterLogin();
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="card" style={{ width: 400, position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#00d4aa" }}>signal·saas</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>信号聚合跟单平台 · 登录</div>
        </div>
        {error && <div className="error-box">{error}</div>}
        <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="label">邮箱</label>
            <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </div>
          <div>
            <label className="label">密码</label>
            <input className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 8 位" />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? "登录中…" : "登 录"}
          </button>
        </form>
        <div style={{ marginTop: 20, fontSize: 13, color: "var(--muted)", textAlign: "center" }}>
          还没有账号？ <Link href="/register" style={{ color: "var(--accent)" }}>立即注册</Link>
        </div>
      </div>
      <RiskDisclosureModal open={riskOpen} onConfirm={onRiskConfirm} />
    </main>
  );
}
