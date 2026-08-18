"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { ToastProvider, useToast } from "@/components/Toast";

type LoginResp = {
  totp_required: boolean;
  challenge_id?: string;
  access_token?: string;
  refresh_token?: string;
  role?: string;
  email?: string;
};

/** M5 T5.1 后台登录（对齐演示稿 admin-login）：品牌面板 + 两步认证（账号密码 → TOTP 双因素）+ 失败锁定提示。 */
function AdminLoginInner() {
  const router = useRouter();
  const toast = useToast();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // TOTP 状态
  const [challengeId, setChallengeId] = useState("");
  const [otp, setOtp] = useState<string[]>(["", "", "", "", "", ""]);
  const [countdown, setCountdown] = useState(30);
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);
  const countdownRef = useRef(0);

  // 已登录直接进后台
  useEffect(() => {
    if (tokenStore.adminAccess) router.replace("/");
  }, [router]);

  // TOTP 30s 倒计时
  useEffect(() => {
    if (step !== 2) return;
    setCountdown(30);
    countdownRef.current = window.setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          window.clearInterval(countdownRef.current);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => window.clearInterval(countdownRef.current);
  }, [step]);

  async function doLogin() {
    if (!email.trim() || !password) {
      setErr("请输入管理员账号和密码");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await apiFetch<LoginResp>("/admin/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (r.totp_required && r.challenge_id) {
        setChallengeId(r.challenge_id);
        setStep(2);
        toast("info", "请输入身份验证器中的 6 位动态码");
        return;
      }
      if (!r.access_token) throw new Error("登录响应异常");
      tokenStore.setAdmin(r.access_token);
      toast("success", `登录成功，欢迎回来 admin`);
      setTimeout(() => router.push("/"), 500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "登录失败");
      toast("error", e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  function handleOtpChange(i: number, v: string) {
    const digit = v.replace(/\D/g, "").slice(-1);
    const next = [...otp];
    next[i] = digit;
    setOtp(next);
    if (digit && i < 5) otpRefs.current[i + 1]?.focus();
    if (next.every((d) => d !== "")) doVerify(next.join(""));
  }

  function handleOtpKey(i: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !otp[i] && i > 0) otpRefs.current[i - 1]?.focus();
  }

  function handleOtpPaste(e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!text) return;
    e.preventDefault();
    const cells = text.split("");
    const next = ["", "", "", "", "", ""];
    cells.forEach((c, i) => (next[i] = c));
    setOtp(next);
    if (cells.length === 6) doVerify(text);
    else otpRefs.current[cells.length]?.focus();
  }

  async function doVerify(code?: string) {
    const value = code || otp.join("");
    if (value.length !== 6) {
      setErr("请输入完整的 6 位验证码");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const r = await apiFetch<LoginResp>("/admin/v1/auth/totp-verify", {
        method: "POST",
        body: JSON.stringify({ challenge_id: challengeId, code: value }),
      });
      if (!r.access_token) throw new Error("验证响应异常");
      tokenStore.setAdmin(r.access_token);
      toast("success", "双因素验证通过");
      setTimeout(() => router.push("/"), 500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "验证失败");
      toast("error", e instanceof Error ? e.message : "验证失败");
      setOtp(["", "", "", "", "", ""]);
      otpRefs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="bg-dots" />
      <div className="bg-sweep" />
      <div className="bg-noise" />

      <div className="auth-wrap">
        {/* 左侧品牌 */}
        <div className="brand-panel">
          <div className="brand-logo">
            <div className="brand-mark">
              <svg viewBox="0 0 32 32" fill="none" width={22} height={22}>
                <path d="M16 1.5 L29 9 V23 L16 30.5 L3 23 V9 Z" fill="#00d4aa" />
                <path d="M11 19.5 v-6 a5 5 0 1 1 10 0 v6 M8.5 22 h5 M18.5 22 h5" stroke="#06281f" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              </svg>
            </div>
            Omni<span style={{ color: "#00d4aa" }}>Alpha</span>
          </div>
          <div>
            <span className="admin-badge">ADMIN CONSOLE</span>
            <div className="brand-title" style={{ marginTop: 12 }}>运营管理后台</div>
            <div className="brand-desc">用户 / 信号源 / 订单 / 支付 / 邀请 / 钱包 / 提现 / 风控 / 审计 · 10 大模块统一管理</div>
          </div>
          <div className="security-list">
            <div className="sec-item"><span className="sec-ic">◈</span> 与用户前台完全隔离的登录体系</div>
            <div className="sec-item"><span className="sec-ic">▣</span> 独立 cookie 域 · 独立 JWT audience</div>
            <div className="sec-item"><span className="sec-ic">☰</span> 所有写操作强制 audit-log 留痕</div>
            <div className="sec-item"><span className="sec-ic">◉</span> RBAC 角色：admin / reviewer / support</div>
          </div>
        </div>

        {/* 右侧认证卡 */}
        <div className="auth-card">
          {/* 步骤 1：账号密码 */}
          <div className={`view${step === 1 ? " active" : ""}`}>
            <div className="card-hdr">
              <span className="admin-badge">ADMIN CONSOLE</span>
              <div className="card-title">管理员登录</div>
              <div className="card-sub">独立入口 · 请勿在公共设备登录</div>
            </div>
            <div className="field">
              <label className="field-label">管理员账号</label>
              <input className="input input-mono" placeholder="admin 前缀账号" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doLogin()} />
            </div>
            <div className="field">
              <label className="field-label">密码</label>
              <input className={`input${err ? " input-err" : ""}`} type="password" placeholder="••••••••" value={password} onChange={(e) => { setPassword(e.target.value); setErr(""); }} onKeyDown={(e) => e.key === "Enter" && doLogin()} />
              {err && <span className="err-msg">{err}</span>}
            </div>
            <div className="security-note">
              <span>⚠</span>
              <span>登录行为将被记录：操作人 / 时间 / IP / 设备</span>
            </div>
            <button className="btn-admin" onClick={doLogin} disabled={busy || !email.trim() || !password}>
              {busy ? "登录中…" : "安全登录"}
            </button>
            <div className="muted-tip">连续 5 次密码错误锁定 15 分钟 · 30 分钟无操作自动登出</div>
          </div>

          {/* 步骤 2：TOTP 双因素（V1.1 启用） */}
          <div className={`view${step === 2 ? " active" : ""}`}>
            <div className="card-hdr">
              <span className="admin-badge">2FA · TOTP</span>
              <div className="card-title">双因素验证</div>
              <div className="card-sub">输入身份验证器中的 6 位动态码</div>
            </div>
            <div className="otp-grid" onPaste={handleOtpPaste}>
              {otp.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => { otpRefs.current[i] = el; }}
                  className={`otp-cell${d ? " filled" : ""}`}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={1}
                  value={d}
                  onChange={(e) => handleOtpChange(i, e.target.value)}
                  onKeyDown={(e) => handleOtpKey(i, e)}
                />
              ))}
            </div>
            {err && <span className="err-msg" style={{ textAlign: "center" }}>{err}</span>}
            <div style={{ textAlign: "center", fontFamily: "var(--font-geist-mono), monospace", fontSize: 12, color: "var(--muted)" }}>
              剩余 {countdown} 秒 {countdown <= 5 ? <span style={{ color: "var(--warning)" }}>· 即将刷新</span> : null}
            </div>
            <button className="btn-admin" onClick={() => doVerify()} disabled={busy || otp.some((d) => !d)}>
              {busy ? "验证中…" : "验证并登录"}
            </button>
            <div className="muted-tip">V1.1 后置启用（TOTP）· V1 版本此步为可选配置项</div>
            <button style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 12, cursor: "pointer" }} onClick={() => { setStep(1); setErr(""); setOtp(["", "", "", "", "", ""]); }}>← 返回上一步</button>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function AdminLoginPage() {
  return (
    <ToastProvider>
      <AdminLoginInner />
    </ToastProvider>
  );
}
