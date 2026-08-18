"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, tokenStore } from "@/lib/api";
import RiskDisclosureModal from "@/components/RiskDisclosureModal";
import AuthBrand from "@/components/AuthBrand";
import { ToastStack, useToasts } from "@/components/Toast";
import { usePlatformConfig } from "@/lib/config";
import * as S from "@/components/authStyles";

/** ★ 登录页：对齐设计稿（双栏品牌区 + 玻璃拟态认证卡 + Tab 滑动高亮 + 忘记密码入口）。 */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [riskOpen, setRiskOpen] = useState(false);
  /** 卡片内视图：login（登录）| forgot（忘记密码，提示型入口） */
  const [view, setView] = useState<"login" | "forgot">("login");
  const [tab, setTab] = useState<"login" | "register">("login");
  const { toasts } = useToasts();
  const cfg = usePlatformConfig();

  /** 响应式：<900px 隐藏品牌区、卡片单列（设计稿 @media max-width:900px） */
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 900px)");
    const update = () => setWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const activated = searchParams.get("activated") === "1";

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
      // 保存邮箱（个人中心概览展示用）
      localStorage.setItem("ss_email", email);
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
    <main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
      <div style={{ ...S.authWrap, gridTemplateColumns: wide ? "1fr 460px" : "1fr", maxWidth: wide ? 1120 : 520 }}>
        {/* 左侧品牌区 */}
        <AuthBrand visible={wide} />

        {/* 右侧玻璃拟态认证卡片 */}
        <div style={S.authCard}>
          {/* Tab 切换（auth-tabs 滑动高亮；注册保留独立路由 /register） */}
          <div style={S.tabsWrap}>
            <div
              style={{
                ...S.tabIndicator,
                transform: tab === "login" ? "translateX(0)" : "translateX(calc(100% + 4px))",
              }}
            />
            <button
              type="button"
              style={{ ...S.tabBtn, color: tab === "login" ? "#06281f" : "var(--muted)", fontWeight: tab === "login" ? 600 : 500 }}
              onClick={() => {
                setTab("login");
                setView("login");
              }}
            >
              登 录
            </button>
            <button
              type="button"
              style={{ ...S.tabBtn, color: tab === "register" ? "#06281f" : "var(--muted)", fontWeight: tab === "register" ? 600 : 500 }}
              onClick={() => router.push("/register")}
            >
              注 册
            </button>
          </div>

          {view === "login" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {activated && (
                <div style={{ background: "rgba(40,196,100,0.1)", border: "1px solid rgba(40,196,100,0.35)", color: "var(--success)", borderRadius: 6, padding: "10px 14px", fontSize: 13 }}>
                  ✓ 邮箱验证成功，请使用新账号登录
                </div>
              )}
              {error && <div className="error-box">{error}</div>}
              <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div style={S.field}>
                  <label style={S.fieldLabel}>邮箱</label>
                  <input
                    className="input"
                    style={{ ...S.input48, ...S.inputMono }}
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                  />
                </div>
                <div style={S.field}>
                  <label style={S.fieldLabel}>
                    密码
                    <a style={S.link} onClick={() => setView("forgot")}>
                      忘记密码？
                    </a>
                  </label>
                  <input
                    className="input"
                    style={S.input48}
                    type="password"
                    required
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError("");
                    }}
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                </div>
                <button className="btn btn-primary" type="submit" disabled={loading} style={S.btnPrimary48}>
                  {loading ? "登录中…" : "登 录"}
                </button>
              </form>
              <div style={S.authFoot}>
                没有账号？ <Link href="/register" style={S.link}>立即注册</Link>
              </div>
            </div>
          ) : (
            /* ★ 忘记密码视图（后端无 forgot/reset 接口 → 仅告知联系管理员，不再提供假的"发送验证码"流程） */
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={S.subTitle}>忘记密码</div>
              <div style={S.riskBox}>
                <span>⚠</span>
                <span>
                  自助密码重置暂未开放。如需重置密码，请联系平台客服，并提供你的注册邮箱与近期订单信息以便核实身份，核实通过后将为重置。
                  {cfg.support.email && (
                    <>
                      <br />
                      客服邮箱：
                      <a href={`mailto:${cfg.support.email}`} style={{ color: "var(--accent)", textDecoration: "none" }}>{cfg.support.email}</a>
                    </>
                  )}
                </span>
              </div>
              <div style={S.authFoot}>
                <a style={S.link} onClick={() => setView("login")}>← 返回登录</a>
              </div>
            </div>
          )}
        </div>
      </div>

      <RiskDisclosureModal open={riskOpen} onConfirm={onRiskConfirm} />
      <ToastStack toasts={toasts} />
    </main>
  );
}
