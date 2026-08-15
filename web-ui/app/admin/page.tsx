"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

/** M5 T5.9 后台概览：各模块快速入口 + 关键指标。 */
export default function AdminDashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<{ users: number; payments: number; withdrawals: number; audit: number } | null>(null);
  const [risk, setRisk] = useState<{ emergency_stop: boolean; daily_loss_limit_usdt: number } | null>(null);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    (async () => {
      try {
        const [u, p, w, a, r] = await Promise.all([
          apiFetch<{ total: number }>("/admin/v1/users?size=1", {}, tokenStore.adminAccess),
          apiFetch<{ total: number }>("/admin/v1/payments?size=1", {}, tokenStore.adminAccess),
          apiFetch<{ total: number }>("/admin/v1/withdrawals?size=1", {}, tokenStore.adminAccess).catch(() => ({ total: 0 })),
          apiFetch<{ total: number }>("/admin/v1/audit?size=1", {}, tokenStore.adminAccess),
          apiFetch<{ emergency_stop: boolean; daily_loss_limit_usdt: number }>("/admin/v1/risk/panel", {}, tokenStore.adminAccess),
        ]);
        setStats({ users: u.total, payments: p.total, withdrawals: w.total, audit: a.total });
        setRisk(r);
      } catch {
        /* ignore */
      }
    })();
  }, [router]);

  const cards = [
    { label: "注册用户", value: stats?.users ?? "-", href: "/admin/users" },
    { label: "支付订单", value: stats?.payments ?? "-", href: "/admin/payments" },
    { label: "提现单", value: stats?.withdrawals ?? "-", href: "/admin/withdrawals" },
    { label: "审计事件", value: stats?.audit ?? "-", href: "/admin/audit" },
  ];

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>概览</div>
      <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>signal·saas 运营后台</div>

      {risk?.emergency_stop && (
        <div style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.5)", color: "#f87171", borderRadius: 6, padding: "12px 16px", fontSize: 13, marginBottom: 20 }}>
          ⚠ 全局紧急制动已开启：所有 OPEN/ADD 跟单将被拒绝，仅放行平仓
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 14 }}>
        {cards.map((c) => (
          <Link key={c.href} href={c.href} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="card" style={{ padding: 20, cursor: "pointer" }}>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>{c.label}</div>
              <div style={{ fontSize: 26, fontWeight: 800, marginTop: 6 }}>{c.value}</div>
              <div style={{ color: "var(--accent)", fontSize: 12, marginTop: 8 }}>进入 →</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
