"use client";

import { Suspense, useEffect, useRef, useState, type CSSProperties } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, tokenStore } from "@/lib/api";
import AuthBrand from "@/components/AuthBrand";
import { ToastStack, useToasts } from "@/components/Toast";
import * as S from "@/components/authStyles";

/** ★ 注册页：对齐设计稿（3 步注册指示器 + 条款勾选 + 密码强度 + 验证码倒计时 + 风险揭示 + 首次引导）。 */
export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}

/** 可选交易所（key 与后端 ALLOWED_EXCHANGES 一致） */
const EXCHANGES = [
  { key: "gate", abbr: "GATE", name: "Gate" },
  { key: "binance", abbr: "BIN", name: "Binance" },
  { key: "okx", abbr: "OKX", name: "OKX" },
  { key: "bybit", abbr: "BYB", name: "Bybit" },
  { key: "bitget", abbr: "BGT", name: "Bitget" },
];

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const invite = searchParams.get("invite") ?? "";
  const next = searchParams.get("next") ?? "";

  /** 注册 3 步：1 邮箱密码 → 2 验证码 → 3 完成（风险揭示） */
  const [step, setStep] = useState<1 | 2 | 3>(1);
  /** 首次引导 5 步：0 未开始 → 1 选所 → 2 交易所码 → 3 好友码 → 4 完成 */
  const [onbStep, setOnbStep] = useState<0 | 1 | 2 | 3 | 4>(0);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [agree, setAgree] = useState(false);
  const [riskChecked, setRiskChecked] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  /** 首次引导表单 */
  const [exchange, setExchange] = useState("");
  const [exInviteCode, setExInviteCode] = useState("");
  const [friendCode, setFriendCode] = useState(invite); // ?invite= 预填
  const [exInviteOk, setExInviteOk] = useState(false);
  const [exInviteErr, setExInviteErr] = useState("");
  const [friendOk, setFriendOk] = useState(false);
  const [friendErr, setFriendErr] = useState("");
  const [onbLoading, setOnbLoading] = useState(false);

  /** 验证码 30s 倒计时 */
  const [, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
    },
    []
  );

  const { toasts, push } = useToasts();

  /** 响应式：<900px 隐藏品牌区、卡片单列 */
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 900px)");
    const update = () => setWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  function startCountdown() {
    if (timerRef.current) clearInterval(timerRef.current);
    setCountdown(30);
    timerRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }

  /** 密码强度实时提示 */
  function pwdStrength(pw: string) {
    if (!pw) return { label: "", level: 0, color: "var(--rule)" };
    const len = pw.length;
    const hasLetter = /[a-zA-Z]/.test(pw);
    const hasDigit = /\d/.test(pw);
    const hasSpecial = /[^a-zA-Z0-9]/.test(pw);
    if (len >= 8 && hasLetter && hasDigit && hasSpecial) return { label: "强度：强", level: 3, color: "var(--success)" };
    if (len >= 8 && hasLetter && hasDigit) return { label: "强度：中", level: 2, color: "var(--warning)" };
    if (len >= 8) return { label: "强度：弱（建议含字母与数字）", level: 1, color: "#f87171" };
    if (len > 0) return { label: "至少 8 位", level: 1, color: "#f87171" };
    return { label: "", level: 0, color: "var(--rule)" };
  }
  const st = pwdStrength(password);

  /** 步骤 1：注册 → 发送验证码 */
  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!agree) {
      push("warn", "请先阅读并同意服务条款与隐私政策");
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      await apiFetch("/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
      setStep(2);
      startCountdown();
      push("info", `验证码已发送至 ${email}（5 分钟有效）`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  }

  /** 步骤 2：验证邮箱 → 自动登录（首次引导的 identity 接口需鉴权） */
  async function onVerify(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code }) });
      const login = await apiFetch<{ access_token: string; refresh_token?: string; risk_disclosure_accepted?: boolean }>(
        "/v1/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) }
      );
      tokenStore.set(login);
      setStep(3);
      push("success", "注册成功，请完成风险揭示与首次引导");
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证失败");
    } finally {
      setLoading(false);
    }
  }

  /** 步骤 3：勾选风险揭示后进入首次引导（尽力同步后端风险确认状态） */
  async function onEnterOnboarding() {
    if (!riskChecked) {
      push("warn", "请先勾选已阅读并同意风险揭示");
      return;
    }
    try {
      await apiFetch("/v1/auth/accept-risk-disclosure", { method: "POST" }, tokenStore.access);
      tokenStore.setRiskAccepted(true);
    } catch {
      /* best-effort：后端不可达时不影响引导流程 */
    }
    setOnbStep(1);
    push("success", "注册成功，开始首次引导");
  }

  /** 引导步骤 1→2：选所 */
  async function onChooseExchange() {
    if (!exchange) {
      push("warn", "请先选择交易所");
      return;
    }
    setOnbLoading(true);
    try {
      await apiFetch("/v1/identity/choose-exchange", { method: "POST", body: JSON.stringify({ exchange }) }, tokenStore.access);
      setOnbStep(2);
    } catch (err) {
      push("error", err instanceof Error ? err.message : "选择交易所失败");
    } finally {
      setOnbLoading(false);
    }
  }

  /** 引导步骤 2→3：校验并绑定交易所邀请码（选填，可跳过） */
  async function onVerifyExchangeInvite() {
    const c = exInviteCode.trim();
    if (!c) {
      push("info", "邀请码为选填项，可直接跳过");
      return;
    }
    setOnbLoading(true);
    try {
      await apiFetch("/v1/identity/bind-exchange-invite", { method: "POST", body: JSON.stringify({ exchange, code: c }) }, tokenStore.access);
      setExInviteOk(true);
      setExInviteErr("");
      const name = EXCHANGES.find((x) => x.key === exchange)?.name ?? exchange;
      push("success", `邀请码已提交（${name}），管理员复核通过后免订阅`);
    } catch (err) {
      setExInviteOk(false);
      setExInviteErr(err instanceof Error ? err.message : "邀请码无效或不属于所选交易所");
    } finally {
      setOnbLoading(false);
    }
  }

  /** 引导步骤 3→4：校验好友邀请码（可选，可跳过） */
  async function onVerifyFriendInvite() {
    const c = friendCode.trim();
    if (!c) {
      push("info", "好友邀请码为选填项，可直接继续");
      return;
    }
    setOnbLoading(true);
    try {
      const res = await apiFetch<{ sub_account?: boolean }>("/v1/identity/bind-invite", { method: "POST", body: JSON.stringify({ code: c }) }, tokenStore.access);
      setFriendOk(true);
      setFriendErr("");
      push("success", res.sub_account ? "命中平台资源池，已自动标记为主号下级（免订阅）" : "好友邀请码绑定成功，享 10% 邀请奖励");
    } catch (err) {
      setFriendOk(false);
      setFriendErr(err instanceof Error ? err.message : "好友邀请码无效，可跳过");
    } finally {
      setOnbLoading(false);
    }
  }

  function onFinish() {
    const target = next && next.startsWith("/") && !next.startsWith("//") && !next.includes(":") ? next : "/account";
    router.push(target);
  }

  const inOnboarding = onbStep > 0;
  const exchangeName = EXCHANGES.find((x) => x.key === exchange)?.name ?? exchange;

  /** 首次引导 5 步指示器紧凑样式（460px 卡片内不溢出） */
  const obSteps: CSSProperties = { ...S.steps, gap: 4 };
  const obStepItem: CSSProperties = { ...S.stepItem, gap: 5, fontSize: 10.5 };
  const obStepNum: CSSProperties = { ...S.stepNum, width: 20, height: 20, fontSize: 10 };
  const obStepLine: CSSProperties = { width: 18, height: 1, background: "rgba(51,65,85,0.6)" };

  return (
    <main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
      <div style={{ ...S.authWrap, gridTemplateColumns: wide ? "1fr 460px" : "1fr", maxWidth: wide ? 1120 : 520 }}>
        {/* 左侧品牌区 */}
        <AuthBrand visible={wide} />

        {/* 右侧玻璃拟态认证卡片 */}
        <div style={S.authCard}>
          {/* Tab 切换（auth-tabs 滑动高亮；登录保留独立路由 /login） */}
          <div style={S.tabsWrap}>
            <div style={{ ...S.tabIndicator, transform: "translateX(calc(100% + 4px))" }} />
            <button type="button" style={{ ...S.tabBtn, color: "var(--muted)", fontWeight: 500 }} onClick={() => router.push("/login")}>
              登 录
            </button>
            <button type="button" style={{ ...S.tabBtn, color: "#06281f", fontWeight: 600 }}>
              注 册
            </button>
          </div>

          {!inOnboarding ? (
            /* ── 注册 3 步流程 ── */
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* 3 步指示器：邮箱 → 验证码 → 完成 */}
              <div style={S.steps}>
                <div style={{ ...S.stepItem, ...(step >= 1 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...S.stepNum, ...(step > 1 ? S.stepDoneNum : step === 1 ? S.stepActiveNum : {}) }}>
                    {step > 1 ? "✓" : "1"}
                  </span>
                  邮箱
                </div>
                <div style={S.stepLine} />
                <div style={{ ...S.stepItem, ...(step >= 2 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...S.stepNum, ...(step > 2 ? S.stepDoneNum : step === 2 ? S.stepActiveNum : {}) }}>
                    {step > 2 ? "✓" : "2"}
                  </span>
                  验证码
                </div>
                <div style={S.stepLine} />
                <div style={{ ...S.stepItem, ...(step >= 3 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...S.stepNum, ...(step === 3 ? S.stepActiveNum : {}) }}>3</span>
                  完成
                </div>
              </div>

              {error && <div className="error-box">{error}</div>}

              {step === 1 && (
                <form onSubmit={onRegister} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {invite && (
                    <div style={{ background: "rgba(0,212,170,0.1)", border: "1px solid rgba(0,212,170,0.35)", color: "var(--accent)", borderRadius: 6, padding: "10px 14px", fontSize: 13 }}>
                      好友邀请注册 · 邀请码 <strong style={{ letterSpacing: 2 }}>{invite}</strong>
                    </div>
                  )}
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
                    <label style={S.fieldLabel}>密码（至少 8 位，含字母与数字）</label>
                    <input
                      className="input"
                      style={S.input48}
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="至少 8 位，含字母与数字"
                      autoComplete="new-password"
                    />
                    {/* 密码强度实时提示 */}
                    {password.length > 0 && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ display: "flex", gap: 4, flex: 1 }}>
                          {[1, 2, 3].map((i) => (
                            <span
                              key={i}
                              style={{
                                flex: 1,
                                height: 4,
                                borderRadius: 2,
                                background: i <= st.level ? st.color : "rgba(51,65,85,0.6)",
                                transition: "background 0.2s",
                              }}
                            />
                          ))}
                        </div>
                        <span style={{ fontSize: 12, color: st.color }}>{st.label}</span>
                      </div>
                    )}
                  </div>
                  <div style={S.field}>
                    <label style={S.fieldLabel}>确认密码</label>
                    <input
                      className="input"
                      style={S.input48}
                      type="password"
                      required
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      placeholder="再次输入密码"
                      autoComplete="new-password"
                    />
                  </div>
                  <label style={S.checkRow}>
                    <input
                      type="checkbox"
                      checked={agree}
                      onChange={(e) => setAgree(e.target.checked)}
                      style={{ width: 16, height: 16, accentColor: "var(--accent)", cursor: "pointer" }}
                    />
                    <span>
                      我已阅读并同意 <a href="/terms" style={S.link}>服务条款</a> 与 <a href="/privacy" style={S.link}>隐私政策</a>
                    </span>
                  </label>
                  <button
                    className="btn btn-primary"
                    type="submit"
                    disabled={loading || !agree}
                    style={S.btnPrimary48}
                  >
                    {loading ? "提交中…" : "获取验证码"}
                  </button>
                </form>
              )}

              {step === 2 && (
                <form onSubmit={onVerify} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={S.field}>
                    <label style={{ ...S.fieldLabel, justifyContent: "flex-start", gap: 8 }}>
                      6 位验证码
                      <span style={S.okMsg}>✓ 已发送至 {email}（5 分钟有效）</span>
                    </label>
                    <div style={S.codeRow}>
                      <input
                        className="input"
                        style={S.codeInput}
                        inputMode="numeric"
                        pattern="[0-9]{6}"
                        maxLength={6}
                        required
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        placeholder="000000"
                      />
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      验证码通过注册发送至您的邮箱；未收到请检查垃圾箱或稍后重试
                      {process.env.NODE_ENV === "development" && (
                        <>。开发环境固定验证码：<strong style={{ color: "var(--accent)" }}>123456</strong></>
                      )}
                    </div>
                  </div>
                  <button className="btn btn-primary" type="submit" disabled={loading} style={S.btnPrimary48}>
                    {loading ? "验证中…" : "验证并注册"}
                  </button>
                </form>
              )}

              {step === 3 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {/* 注册成功视图 */}
                  <div style={{ textAlign: "center", padding: "8px 0" }}>
                    <div style={S.doneIcon}>✓</div>
                    <div style={{ ...S.subTitle, marginTop: 4 }}>注册成功</div>
                    <div style={S.subDesc}>欢迎加入 OmniAlpha</div>
                  </div>
                  <div style={S.riskBox}>
                    <span>⚠</span>
                    <span>合约交易具有高风险，可能导致全部本金损失。本平台仅提供信号聚合工具，不承诺任何收益。</span>
                  </div>
                  <label style={S.checkRow}>
                    <input
                      type="checkbox"
                      checked={riskChecked}
                      onChange={(e) => setRiskChecked(e.target.checked)}
                      style={{ width: 16, height: 16, accentColor: "var(--accent)", cursor: "pointer" }}
                    />
                    <span>我已阅读并同意 <a href="/terms" style={S.link}>风险揭示</a>，自愿承担交易风险</span>
                  </label>
                  <button className="btn btn-primary" type="button" disabled={!riskChecked} style={S.btnPrimary48} onClick={onEnterOnboarding}>
                    进入首次引导
                  </button>
                </div>
              )}

              <div style={S.authFoot}>
                已有账号？ <a style={S.link} onClick={() => router.push("/login")}>去登录</a>
              </div>
            </div>
          ) : (
            /* ── 首次引导 5 步流程（选所 → 交易所邀请码 → 好友邀请码 → 完成）── */
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={obSteps}>
                <div style={{ ...obStepItem, ...S.stepActiveColor }}>
                  <span style={{ ...obStepNum, ...S.stepDoneNum }}>✓</span>激活
                </div>
                <div style={obStepLine} />
                <div style={{ ...obStepItem, ...(onbStep >= 1 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...obStepNum, ...(onbStep > 1 ? S.stepDoneNum : onbStep === 1 ? S.stepActiveNum : {}) }}>
                    {onbStep > 1 ? "✓" : "2"}
                  </span>
                  选所
                </div>
                <div style={obStepLine} />
                <div style={{ ...obStepItem, ...(onbStep >= 2 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...obStepNum, ...(onbStep > 2 ? S.stepDoneNum : onbStep === 2 ? S.stepActiveNum : {}) }}>
                    {onbStep > 2 ? "✓" : "3"}
                  </span>
                  交易所码
                </div>
                <div style={obStepLine} />
                <div style={{ ...obStepItem, ...(onbStep >= 3 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...obStepNum, ...(onbStep > 3 ? S.stepDoneNum : onbStep === 3 ? S.stepActiveNum : {}) }}>
                    {onbStep > 3 ? "✓" : "4"}
                  </span>
                  好友码
                </div>
                <div style={obStepLine} />
                <div style={{ ...obStepItem, ...(onbStep >= 4 ? S.stepActiveColor : {}) }}>
                  <span style={{ ...obStepNum, ...(onbStep === 4 ? S.stepActiveNum : {}) }}>5</span>
                  完成
                </div>
              </div>

              {/* 步骤 1：选所 */}
              {onbStep === 1 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <div style={S.subTitle}>选择所属交易所</div>
                    <div style={{ ...S.subDesc, marginTop: 4 }}>你的跟单机器人将部署在该交易所（可后续切换）</div>
                  </div>
                  <div style={S.exchangeGrid}>
                    {EXCHANGES.map((ex) => {
                      const selected = exchange === ex.key;
                      return (
                        <div
                          key={ex.key}
                          style={{ ...S.exchangeCard, ...(selected ? S.exchangeCardSel : {}) }}
                          onClick={() => setExchange(ex.key)}
                        >
                          <div style={{ ...S.exIc, ...(selected ? S.exIcSel : {}) }}>{ex.abbr}</div>
                          <div style={S.exName}>{ex.name}</div>
                        </div>
                      );
                    })}
                  </div>
                  <button className="btn btn-primary" type="button" disabled={!exchange || onbLoading} style={S.btnPrimary48} onClick={onChooseExchange}>
                    {onbLoading ? "提交中…" : "下一步"}
                  </button>
                </div>
              )}

              {/* 步骤 2：交易所邀请码（选填，可跳过） */}
              {onbStep === 2 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <div style={S.subTitle}>
                      填写 <span style={{ color: "var(--accent)" }}>{exchangeName}</span> 邀请码{" "}
                      <span style={{ fontSize: 10, color: "var(--tertiary)" }}>选填 · 可跳过</span>
                    </div>
                    <div style={{ ...S.subDesc, marginTop: 4 }}>
                      在 <strong style={{ color: "var(--fg)" }}>{exchangeName}</strong> 注册时使用的平台邀请码（合作返佣归属核实）；没有可直接跳过
                    </div>
                  </div>
                  <div style={S.field}>
                    <label style={S.fieldLabel}>交易所邀请码（选填）</label>
                    <div style={S.codeRow}>
                      <input
                        className="input"
                        style={{ ...S.input48, ...S.inputMono }}
                        value={exInviteCode}
                        onChange={(e) => {
                          setExInviteCode(e.target.value);
                          setExInviteOk(false);
                          setExInviteErr("");
                        }}
                        placeholder={`如：8F3K2A（对应 ${exchangeName}）`}
                      />
                      <button className="btn btn-secondary" type="button" style={S.sendBtn} disabled={onbLoading} onClick={onVerifyExchangeInvite}>
                        {onbLoading ? "校验中…" : "校验"}
                      </button>
                    </div>
                    {exInviteOk && <span style={S.okMsg}>✓ 邀请码已提交，管理员复核通过后即享免订阅</span>}
                    {exInviteErr && <span style={S.errMsg}>{exInviteErr}</span>}
                  </div>
                  <button
                    className="btn btn-primary"
                    type="button"
                    disabled={onbLoading}
                    style={S.btnPrimary48}
                    onClick={() => setOnbStep(3)}
                  >
                    {exInviteOk ? "下一步" : "跳过并继续"}
                  </button>
                </div>
              )}

              {/* 步骤 3：好友邀请码（可选） */}
              {onbStep === 3 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <div style={S.subTitle}>
                      绑定好友邀请码 <span style={{ fontSize: 10, color: "var(--tertiary)" }}>可跳过</span>
                    </div>
                    <div style={{ ...S.subDesc, marginTop: 4 }}>
                      绑定后享 10% 邀请奖励；命中平台池自动标记主号下级免订阅
                    </div>
                  </div>
                  <div style={S.field}>
                    <label style={S.fieldLabel}>好友邀请码</label>
                    <div style={S.codeRow}>
                      <input
                        className="input"
                        style={{ ...S.input48, ...S.inputMono }}
                        value={friendCode}
                        onChange={(e) => {
                          setFriendCode(e.target.value);
                          setFriendOk(false);
                          setFriendErr("");
                        }}
                        placeholder="6 位邀请码，如：8F3K2A"
                      />
                      <button className="btn btn-secondary" type="button" style={S.sendBtn} disabled={onbLoading} onClick={onVerifyFriendInvite}>
                        {onbLoading ? "校验中…" : "校验"}
                      </button>
                    </div>
                    {friendOk && <span style={S.okMsg}>✓ 好友邀请码绑定成功，享 10% 邀请奖励</span>}
                    {friendErr && <span style={S.errMsg}>{friendErr}（可跳过）</span>}
                  </div>
                  <button className="btn btn-primary" type="button" style={S.btnPrimary48} onClick={() => setOnbStep(4)}>
                    继续
                  </button>
                </div>
              )}

              {/* 步骤 4：完成 */}
              {onbStep === 4 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ textAlign: "center", padding: "8px 0" }}>
                    <div style={S.doneIcon}>✓</div>
                    <div style={{ ...S.subTitle, marginTop: 4 }}>引导完成</div>
                    <div style={S.subDesc}>下一步：绑定交易所 API Key 开启跟单</div>
                  </div>
                  <button className="btn btn-primary" type="button" style={S.btnPrimary48} onClick={onFinish}>
                    进入首页
                  </button>
                  <button className="btn btn-secondary" type="button" style={S.btnSecondary48} onClick={() => router.push("/account")}>
                    绑定 API Key
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <ToastStack toasts={toasts} />
    </main>
  );
}
