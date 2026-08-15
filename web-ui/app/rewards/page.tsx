"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Balance = { total_usdt: number; available_usdt: number; withdrawing_usdt: number; paid_usdt: number; frozen_usdt: number };
type LedgerItem = { id: number; amount_usdt: number; status: string; verifying_ends_at: string | null };

const STATUS_LABEL: Record<string, string> = {
  verifying: "核实中", available: "可提现", withdrawing: "提现中",
  paid: "已发放", frozen: "冻结", canceled: "已取消", paid_failed: "发放失败", rolled_back: "已回滚",
};

/** M4 T4.11 奖励余额：★G12 5 字段 + 24h/48h 核实倒计时 + 流水。 */
export default function RewardsPage() {
  const router = useRouter();
  const [bal, setBal] = useState<Balance | null>(null);
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [now, setNow] = useState(Date.now());
  // ★ 状态筛选 + 分页（前端本地）
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);

  const FILTERS: Array<[string, string]> = [
    ["all", "全部"],
    ["verifying", "核实中"],
    ["available", "可提现"],
    ["withdrawing", "提现中"],
    ["paid", "已发放"],
    ["frozen", "冻结"],
  ];
  const PAGE_SIZE = 10;
  const filtered = filter === "all" ? ledger : ledger.filter((i) => i.status === filter);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const load = useCallback(async () => {
    try {
      const [b, l] = await Promise.all([
        apiFetch<Balance>("/v1/rewards/balance", {}, tokenStore.access),
        apiFetch<{ items: LedgerItem[] }>("/v1/rewards/ledger", {}, tokenStore.access),
      ]);
      setBal(b);
      setLedger(l.items);
    } catch {
      /* token 失效由路由保护 */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    load();
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [load, router]);

  function countdown(iso: string | null): string {
    if (!iso) return "";
    const end = new Date(iso).getTime();
    const diff = Math.max(0, end - now);
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    const s = Math.floor((diff % 60_000) / 1000);
    return `${h}时 ${m}分 ${s}秒`;
  }

  const cards: Array<[string, number | undefined, string]> = [
    ["累计奖励", bal?.total_usdt, ""],
    ["可提现", bal?.available_usdt, "success"],
    ["提现中", bal?.withdrawing_usdt, ""],
    ["已提现", bal?.paid_usdt, ""],
    ["冻结（核实中）", bal?.frozen_usdt, "warning"],
  ];

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>奖励余额</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>邀请奖励 · 10% 返佣 · 24h/48h 核实</div>
        </div>

        {/* ★ G12 5 字段 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 24 }}>
          {cards.map(([label, val, tone]) => (
            <div key={label} className="card" style={{ padding: 18 }}>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>{label}</div>
              <div style={{ fontSize: 20, fontWeight: 800, marginTop: 6, color: tone === "success" ? "var(--success)" : tone === "warning" ? "var(--warning)" : "var(--fg)" }}>
                {(val ?? 0).toFixed(2)} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>USDT</span>
              </div>
            </div>
          ))}
        </div>

        <Link href="/withdraw" style={{ display: "inline-block", marginBottom: 28 }}>
          <button className="btn btn-primary">申请提现（≥10U，手续费 1U）</button>
        </Link>

        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 12 }}>奖励流水</div>

          {/* ★ 状态筛选 Tabs */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            {FILTERS.map(([key, label]) => {
              const count = key === "all" ? ledger.length : ledger.filter((i) => i.status === key).length;
              return (
                <button
                  key={key}
                  onClick={() => { setFilter(key); setPage(1); }}
                  style={{
                    padding: "4px 12px", borderRadius: 16, fontSize: 12, cursor: "pointer",
                    border: filter === key ? "1px solid var(--accent)" : "1px solid var(--rule)",
                    background: filter === key ? "var(--accent-soft)" : "transparent",
                    color: filter === key ? "var(--accent)" : "var(--muted)",
                  }}
                >
                  {label} {count}
                </button>
              );
            })}
          </div>

          {pageItems.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13, padding: "16px 0" }}>该状态下暂无奖励记录</div>
          ) : (
            pageItems.map((item) => (
              <div key={item.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--rule)", fontSize: 13 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>+{item.amount_usdt.toFixed(2)} USDT</div>
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>
                    {item.status === "verifying" && item.verifying_ends_at
                      ? `核实倒计时 ${countdown(item.verifying_ends_at)}`
                      : STATUS_LABEL[item.status] || item.status}
                  </div>
                </div>
                <span style={{ fontSize: 12, padding: "3px 10px", borderRadius: 20, background: item.status === "available" ? "rgba(40,196,100,.15)" : "rgba(100,116,139,.15)", color: item.status === "available" ? "var(--success)" : "var(--muted)" }}>
                  {STATUS_LABEL[item.status] || item.status}
                </span>
              </div>
            ))
          )}

          {/* ★ 分页 */}
          {totalPages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: 8, alignItems: "center", paddingTop: 14 }}>
              <button className="btn btn-secondary" style={{ padding: "4px 12px", fontSize: 12 }} disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
              <span style={{ fontSize: 13, color: "var(--muted)" }}>{page} / {totalPages}</span>
              <button className="btn btn-secondary" style={{ padding: "4px 12px", fontSize: 12 }} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
