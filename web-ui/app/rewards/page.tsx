"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Balance = { total_usdt: number; available_usdt: number; withdrawing_usdt: number; paid_usdt: number; frozen_usdt: number };
type LedgerItem = { id: number; amount_usdt: number; status: string; verifying_ends_at: string | null; created_at?: string | null };

const STATUS_META: Record<string, { label: string; cls: string }> = {
  verifying: { label: "核实中", cls: "badge-warn" },
  available: { label: "可提现", cls: "badge-ok" },
  withdrawing: { label: "提现中", cls: "badge-info" },
  paid: { label: "已发放", cls: "badge-ok" },
  frozen: { label: "冻结", cls: "badge-err" },
  canceled: { label: "已取消", cls: "badge-err" },
  paid_failed: { label: "发放失败", cls: "badge-err" },
  rolled_back: { label: "已回滚", cls: "badge-muted" },
};

/** M4 T4.11 奖励余额：★G12 5 字段（首卡高亮）+ 6 列流水 + 筛选角标 + 方块分页 + 倒计时。 */
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
  const PAGE_SIZE = 8;
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
    return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  }

  const cards: Array<{ label: string; val: number | undefined; color?: string; sub: string; highlight?: boolean }> = [
    { label: "可提现余额", val: bal?.available_usdt, color: "var(--accent)", sub: "USDT · 可立即申请提现", highlight: true },
    { label: "累计奖励", val: bal?.total_usdt, sub: "USDT · 所有记录 SUM（含取消/回滚）" },
    { label: "提现中", val: bal?.withdrawing_usdt, color: "#60a5fa", sub: "USDT · 审核 / 打款中" },
    { label: "已提现", val: bal?.paid_usdt, color: "var(--muted)", sub: "USDT · 含链上 TxHash" },
    { label: "冻结", val: bal?.frozen_usdt, color: "var(--danger)", sub: "USDT · 48h 风控核实中（G11）" },
  ];

  function remark(item: LedgerItem): string {
    switch (item.status) {
      case "verifying": return `24h 核实 · 剩余 ${countdown(item.verifying_ends_at)}`;
      case "frozen": return "48h 风控核实（G11）";
      case "available": return "核实通过 · 已计入可提现";
      case "withdrawing": return "已发起提现";
      case "paid": return "已转入提现流程 · TxHash 已记录";
      case "canceled": return "下级退款 · 奖励回滚";
      case "rolled_back": return "奖励回滚（风控）";
      case "paid_failed": return "发放失败 · 异常池";
      default: return "—";
    }
  }

  const pageNums = Array.from({ length: totalPages }, (_, i) => i + 1);
  const startPage = Math.max(1, Math.min(page - 2, totalPages - 4));
  const visiblePages = pageNums.slice(startPage - 1, startPage + 4);

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div className="page-wrap">
        {/* 页头 + 右上"提现"大按钮 */}
        <div className="page-hdr">
          <div>
            <div className="page-eyebrow">REWARD BALANCE · 奖励余额</div>
            <h1 className="page-title">奖励余额<small>邀请奖励 · 5 字段账本</small></h1>
          </div>
          <div className="page-actions">
            <Link href="/withdraw">
              <button className="btn btn-primary" style={{ height: 44, padding: "0 32px", fontSize: 15 }}>提现</button>
            </Link>
          </div>
        </div>

        {/* 5 字段账本：首卡 accent 渐变 + 实线顶 + 28px 数字 */}
        <div className="kpi-grid" style={{ marginBottom: 24 }}>
          {cards.map((c) => (
            <div
              key={c.label}
              className="kpi-card"
              style={
                c.highlight
                  ? { borderColor: "rgba(0,212,170,0.45)", background: "linear-gradient(135deg, rgba(0,212,170,0.06), var(--surface))", borderTop: "2px solid var(--accent)" }
                  : undefined
              }
            >
              <div className="kpi-l">{c.label}</div>
              <div className="kpi-v" style={{ fontSize: c.highlight ? 28 : 26, color: c.color }}>
                {(c.val ?? 0).toFixed(2)}
              </div>
              <div className="kpi-s">{c.sub}</div>
            </div>
          ))}
        </div>

        {/* 奖励流水：6 列 ftx-table + 筛选角标 + 方块分页 */}
        <div className="panel">
          <div className="panel-hdr">
            <div className="panel-title"><span className="sec-dot"></span>奖励流水</div>
            <span className="panel-sub">时间 / 来源 / 下级 / 金额 / 状态 / 备注</span>
          </div>

          {/* 状态筛选 Tabs（数量角标） */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {FILTERS.map(([key, label]) => {
              const count = key === "all" ? ledger.length : ledger.filter((i) => i.status === key).length;
              return (
                <button
                  key={key}
                  className={`chip${filter === key ? " active" : ""}`}
                  onClick={() => { setFilter(key); setPage(1); }}
                >
                  {label} <span style={{ fontFamily: "var(--font-geist-mono), monospace", opacity: 0.75 }}>{count}</span>
                </button>
              );
            })}
          </div>

          {pageItems.length === 0 ? (
            <div className="empty-state" style={{ minHeight: 180 }}>
              <div className="es-ic">◇</div>
              <div style={{ fontSize: 13 }}>该状态下暂无奖励记录</div>
            </div>
          ) : (
            <table className="ftx-table">
              <thead>
                <tr><th>时间</th><th>来源</th><th>下级</th><th className="num">金额</th><th>状态</th><th>备注</th></tr>
              </thead>
              <tbody>
                {pageItems.map((item) => {
                  const st = STATUS_META[item.status] || { label: item.status, cls: "badge-muted" };
                  const negative = item.status === "canceled" || item.status === "rolled_back";
                  return (
                    <tr key={item.id}>
                      <td className="num">{item.created_at ? item.created_at.slice(0, 16) : "—"}</td>
                      <td>{negative ? "奖励回滚" : "订阅奖励"}</td>
                      <td>—</td>
                      <td className="num" style={{ color: negative ? "var(--danger)" : "var(--success)" }}>
                        {negative ? "-" : "+"}{item.amount_usdt.toFixed(2)} U
                      </td>
                      <td><span className={`badge ${st.cls}`}>{st.label}</span></td>
                      <td className="sub-ref">{remark(item)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {/* 页码方块分页 */}
          {totalPages > 1 && (
            <div className="pagination">
              <button className="page-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
              {startPage > 1 && <span style={{ fontSize: 12, color: "var(--tertiary)" }}>…</span>}
              {visiblePages.map((n) => (
                <button key={n} className={`page-btn${n === page ? " active" : ""}`} onClick={() => setPage(n)}>
                  {n}
                </button>
              ))}
              {startPage + 4 < totalPages && <span style={{ fontSize: 12, color: "var(--tertiary)" }}>…</span>}
              <button className="page-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>›</button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
