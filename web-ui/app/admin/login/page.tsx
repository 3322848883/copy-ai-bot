"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

/** M5 T5.1 后台登录（独立 aud=admin 会话）。 */
export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const r = await apiFetch<{ access_token: string; role: string }>("/admin/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      tokenStore.setAdmin(r.access_token);
      router.push("/admin");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ width: 380, maxWidth: "92vw", position: "relative", zIndex: 1 }}>
        <div style={{ textAlign: "center", fontSize: 20, fontWeight: 800, marginBottom: 24 }}>⚡ signal·saas 后台管理</div>
        <div className="card" style={{ padding: 28 }}>
          <label className="label">管理员邮箱</label>
          <input className="input" style={{ width: "100%", marginBottom: 14 }} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@example.com" />
          <label className="label">密码</label>
          <input className="input" style={{ width: "100%", marginBottom: 14 }} type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
          {err && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{err}</div>}
          <button className="btn btn-primary" style={{ width: "100%" }} onClick={submit} disabled={busy || !email || !password}>
            {busy ? "登录中…" : "登录"}
          </button>
        </div>
      </div>
    </main>
  );
}
