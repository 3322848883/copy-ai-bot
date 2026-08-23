"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type FollowStrategy = {
  id: number;
  display_name: string;
  style: string;
  max_drawdown: number;
};

const STYLE_LABEL: Record<string, string> = { trend: "趋势", range: "震荡", momentum: "动量" };
const STYLE_TAG: Record<string, string> = { trend: "tag-trend", range: "tag-range", momentum: "tag-momentum" };

const RATIO_OPTIONS: Array<{ label: string; mode: "fixed" | "percent"; value: number | null }> = [
  { label: "固定金额", mode: "fixed", value: null },
  { label: "比例 10%", mode: "percent", value: 10 },
  { label: "比例 20%", mode: "percent", value: 20 },
  { label: "比例 30%", mode: "percent", value: 30 },
  { label: "比例 50%", mode: "percent", value: 50 },
];

/** ★ 跟单弹窗（策略广场 / 策略详情共用，保证两处设置完全一致）：
 *  杠杆倍数 / 保证金模式 / 跟单比例（固定金额+比例）/ 单笔最大名义价值 / 模拟盘 / 风控提示 / 首次跟单风险揭示确认。 */
export default function FollowModal({
  strategy,
  onClose,
}: {
  strategy: FollowStrategy | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const [form, setForm] = useState({
    leverage: 10,
    margin_mode: "isolated",
    ratio: "比例 20%",
    fixedAmount: 500,
    maxNotional: 10000,
    paper: false,
  });
  const [formMsg, setFormMsg] = useState("");
  if (!strategy) return null;
  const s = strategy;

  async function createBot() {
    setFormMsg("");
    try {
      if (!tokenStore.access) {
        router.push("/login");
        return;
      }
      // ★ 首次跟单强制确认风险揭示（后端 create_bot 亦强制校验）
      if (!tokenStore.riskAccepted) {
        if (!window.confirm("跟单交易具有高风险，可能导致全部本金损失。\n阅读并同意《服务条款》与《风险揭示》后，确认继续？")) {
          return;
        }
        try {
          await apiFetch("/v1/auth/accept-risk-disclosure", { method: "POST" }, tokenStore.access);
          tokenStore.setRiskAccepted(true);
        } catch {
          setFormMsg("风险揭示确认失败，请稍后再试");
          return;
        }
      }
      const keys = await apiFetch<{ items: Array<{ exchange: string; id: number }> }>("/v1/apikeys", {}, tokenStore.access);
      // 跨所跟单：绑定任意交易所 API 即可跟单任意信号源，优选 Gate
      const bound = keys.items ?? [];
      const key = bound.find((k) => k.exchange === "gate") ?? bound[0];
      if (!key) {
        setFormMsg("请先到「我的账户」绑定任一交易所 API Key 后再开启跟单");
        return;
      }
      const ratio = RATIO_OPTIONS.find((o) => o.label === form.ratio) ?? RATIO_OPTIONS[2];
      if (ratio.mode === "fixed" && !(form.fixedAmount > 0)) {
        setFormMsg("请输入大于 0 的固定跟单金额");
        return;
      }
      if (!(form.maxNotional > 0)) {
        setFormMsg("请输入大于 0 的单笔最大名义价值");
        return;
      }
      await apiFetch(
        "/v1/bots",
        {
          method: "POST",
          body: JSON.stringify({
            strategy_id: s.id, exchange: key.exchange, api_key_id: key.id,
            amount_mode: ratio.mode,
            percent: ratio.mode === "percent" ? ratio.value : null,
            fixed_amount_usdt: ratio.mode === "fixed" ? form.fixedAmount : null,
            leverage: form.leverage,
            margin_mode: form.margin_mode,
            max_total_position_usdt: form.maxNotional,
            paper: form.paper,
          }),
        },
        tokenStore.access
      );
      setFormMsg("跟单机器人已创建");
      setTimeout(() => { onClose(); router.push("/bots"); }, 900);
    } catch (e) {
      setFormMsg(e instanceof Error ? e.message : "创建失败");
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.8)", backdropFilter: "blur(4px)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={(e) => { if (e.target === e.currentTarget) { onClose(); setFormMsg(""); } }}
    >
      <div style={{ width: 520, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, boxShadow: "0 16px 48px rgba(0,0,0,0.45)", padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>开启跟单</div>
          <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => { onClose(); setFormMsg(""); }}>✕</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {strategy.display_name} · <span className={`tag ${STYLE_TAG[strategy.style] ?? ""}`}>{STYLE_LABEL[strategy.style] ?? strategy.style}</span>
          <span className="badge badge-ok">运行中</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label className="label">杠杆倍数</label>
            <select className="input" value={form.leverage} onChange={(e) => setForm({ ...form, leverage: Number(e.target.value) })}>
              {[10, 5, 3, 1].map((lv) => <option key={lv} value={lv}>{lv}×</option>)}
            </select>
          </div>
          <div>
            <label className="label">保证金模式</label>
            <select className="input" value={form.margin_mode} onChange={(e) => setForm({ ...form, margin_mode: e.target.value })}>
              <option value="isolated">逐仓</option>
              <option value="cross">全仓</option>
            </select>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label className="label">跟单比例</label>
            <select className="input" value={form.ratio} onChange={(e) => setForm({ ...form, ratio: e.target.value })}>
              {RATIO_OPTIONS.map((o) => <option key={o.label} value={o.label}>{o.label}</option>)}
            </select>
          </div>
          {form.ratio === "固定金额" && (
            <div>
              <label className="label">固定金额（USDT/笔）</label>
              <input
                className="input"
                type="number" min={1}
                value={form.fixedAmount}
                onChange={(e) => setForm({ ...form, fixedAmount: Number(e.target.value) })}
                placeholder="例：500"
              />
            </div>
          )}
        </div>
        <div>
          <label className="label">单笔最大名义价值（风控上限）</label>
          <input
            className="input"
            type="number" min={1}
            value={form.maxNotional}
            onChange={(e) => setForm({ ...form, maxNotional: Number(e.target.value) })}
            placeholder="例：10000（默认 10000 USDT）"
          />
        </div>
        <label className="label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 0 }}>
          <input type="checkbox" checked={form.paper} onChange={(e) => setForm({ ...form, paper: e.target.checked })} />
          模拟盘（沙箱验证，不触达真实资金）
        </label>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: 12, borderRadius: 6, background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: 12, color: "var(--warning)" }}>
          <span>⚠</span>
          <span>本策略为高风险合约交易，历史最大回撤 {strategy.max_drawdown.toFixed(1)}%。我已阅读并同意<Link href="/terms" style={{ color: "var(--warning)" }}>风险揭示</Link>。</span>
        </div>
        {formMsg && (
          <div style={{ color: formMsg.includes("已创建") ? "var(--success)" : "var(--danger)", fontSize: 13 }}>{formMsg}</div>
        )}
        <button className="btn btn-primary" style={{ height: 48, fontSize: 15, fontWeight: 600, width: "100%" }} onClick={createBot}>
          确认开启跟单
        </button>
      </div>
    </div>
  );
}
