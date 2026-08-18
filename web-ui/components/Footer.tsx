"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/Brand";
import { usePlatformConfig } from "@/lib/config";

const COLS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "产品",
    links: [
      { href: "/strategies", label: "策略广场" },
      { href: "/subscriptions", label: "订阅套餐" },
      { href: "/bots", label: "我的跟单" },
    ],
  },
  {
    title: "账户",
    links: [
      { href: "/account", label: "账户中心" },
      { href: "/rewards", label: "奖励余额" },
      { href: "/invite", label: "邀请中心" },
    ],
  },
  {
    title: "支持",
    links: [
      { href: "/terms", label: "服务条款" },
      { href: "/privacy", label: "隐私政策" },
      { href: "/subscriptions", label: "支付指南" },
    ],
  },
];

/** 全站页脚：品牌 + 导航 + 风险提示 + 版权（登录/注册页隐藏）。 */
export default function Footer() {
  const pathname = usePathname();
  const cfg = usePlatformConfig();
  if (pathname === "/login" || pathname === "/register") return null;

  const tg = cfg.support.telegram.trim();
  const tgHref = tg ? (tg.startsWith("http") ? tg : `https://t.me/${tg.replace(/^@/, "")}`) : "";

  return (
    <footer style={{ borderTop: "1px solid var(--rule)", marginTop: 64, background: "rgba(7,14,26,0.6)" }}>
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "40px 24px 24px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 40, justifyContent: "space-between" }}>
          <div style={{ maxWidth: 360 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <BrandMark />
              <span style={{ fontSize: 16, fontWeight: 700, color: "var(--fg)" }}>
                Omni<span style={{ color: "var(--accent)" }}>Alpha</span>
              </span>
            </div>
            <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.8, marginTop: 12 }}>
              AI 驱动的信号聚合与自动执行引擎。7×24 扫描全市场信号，智能识别、自动执行、秒级跟单。你的资金，你的账户，你的 Alpha。
            </p>
          </div>
          {COLS.map((c) => (
            <div key={c.title}>
              <div style={{ fontSize: 11, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>{c.title}</div>
              {c.links.map((l) => (
                <Link key={l.href + l.label} href={l.href} style={{ display: "block", fontSize: 12.5, color: "var(--muted)", textDecoration: "none", marginBottom: 8 }}>
                  {l.label}
                </Link>
              ))}
            </div>
          ))}
          {(cfg.support.email || tg) && (
            <div>
              <div style={{ fontSize: 11, color: "var(--tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>客服</div>
              {cfg.support.email && (
                <a href={`mailto:${cfg.support.email}`} style={{ display: "block", fontSize: 12.5, color: "var(--muted)", textDecoration: "none", marginBottom: 8 }}>
                  {cfg.support.email}
                </a>
              )}
              {tg && (
                <a href={tgHref} target="_blank" rel="noreferrer" style={{ display: "block", fontSize: 12.5, color: "var(--muted)", textDecoration: "none", marginBottom: 8 }}>
                  Telegram {tg.startsWith("@") ? tg : `@${tg}`}
                </a>
              )}
            </div>
          )}
        </div>

        <div style={{ marginTop: 32, paddingTop: 16, borderTop: "1px solid var(--rule)" }}>
          <p style={{ fontSize: 10.5, color: "var(--tertiary)", lineHeight: 1.8 }}>
            风险提示：数字资产合约交易具有极高风险，价格波动剧烈，可能导致本金全部损失。本平台提供的信号与自动化工具仅为辅助决策参考，不构成任何投资建议。历史表现不代表未来收益，请充分评估自身风险承受能力后谨慎参与。
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
            <span style={{ fontSize: 11, color: "var(--tertiary)" }}>© {new Date().getFullYear()} OmniAlpha. All rights reserved.</span>
            <span style={{ fontSize: 10.5, color: "var(--tertiary)" }}>
              <Link href="/terms" style={{ color: "var(--tertiary)", textDecoration: "none" }}>服务条款</Link>
              <span style={{ margin: "0 8px" }}>·</span>
              <Link href="/privacy" style={{ color: "var(--tertiary)", textDecoration: "none" }}>隐私政策</Link>
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
