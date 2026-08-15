"use client";

import Link from "next/link";

/** 隐私政策（合规 M6 T6.1；上线前需外部法务复核）。 */
export default function PrivacyPage() {
  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 820, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <Link href="/" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>← 返回首页</Link>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: "16px 0 8px" }}>隐私政策</h1>
        <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 24 }}>更新日期：2026-08-15 · 本文件为平台基础模板，正式上线前需外部法务复核</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20, fontSize: 14, lineHeight: 1.8 }}>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>1. 我们收集哪些信息</h2>
            <p style={{ color: "var(--muted)" }}>
              注册邮箱、密码密文（bcrypt）、交易所 API Key（AES-256-GCM 加密存储）、邀请关系、跟单配置与订单记录、提现地址、支付交易哈希（公开链上信息）。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>2. 信息的存储与保护</h2>
            <p style={{ color: "var(--muted)" }}>
              API Key 使用 AES-256-GCM 加密后存储，解密即用即弃；传输全程 TLS 加密；后台操作全部留痕审计。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>3. 第三方共享</h2>
            <p style={{ color: "var(--muted)" }}>
              仅在提供服务所必需时与以下主体交互：您绑定的交易所（代您执行跟单）、区块链网络与区块浏览器（支付确认）、邮件服务商（验证码/通知）。我们不出售您的个人数据。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>4. 用户权利</h2>
            <p style={{ color: "var(--muted)" }}>
              您可申请导出或删除账户数据（含解绑 API Key）。删除请求将在 30 日内处理；依法保留的财务与审计记录除外。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>5. 联系我们</h2>
            <p style={{ color: "var(--muted)" }}>隐私相关疑问可通过平台客服渠道与我们联系。</p>
          </section>
        </div>
      </div>
    </main>
  );
}
