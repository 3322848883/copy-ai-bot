"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type InviteItem = { invitee_email: string; bound_at: string; reward_usdt: number; reward_status: string; verifying_ends_at: string | null };
type Risk = { risk_flag: boolean };
type Stats = { total_invitees: number; total_reward: number; verifying_reward: number; available_reward: number };

const STATUS_LABEL: Record<string, string> = {
  verifying: "核实中", available: "可提现", withdrawing: "提现中",
  paid: "已发放", frozen: "冻结", canceled: "已取消", paid_failed: "发放失败", rolled_back: "已回滚",
};

/** M4 T4.10 邀请中心：专属码 + 邀请列表 + 24h/48h 核实状态。 */
export default function InvitePage() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [risk, setRisk] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [msg, setMsg] = useState("");
  const [posterOpen, setPosterOpen] = useState(false);
  const posterRef = useRef<HTMLCanvasElement>(null);

  const shareUrl = typeof window !== "undefined" ? `${window.location.origin}/register?invite=${code}` : "";

  const load = useCallback(async () => {
    try {
      const [c, list, r, s] = await Promise.all([
        apiFetch<{ code: string }>("/v1/referrals/code", {}, tokenStore.access),
        apiFetch<{ items: InviteItem[] }>("/v1/referrals/invites", {}, tokenStore.access),
        apiFetch<Risk>("/v1/referrals/risk", {}, tokenStore.access),
        apiFetch<Stats>("/v1/referrals/stats", {}, tokenStore.access),
      ]);
      setCode(c.code);
      setInvites(list.items);
      setRisk(r.risk_flag);
      setStats(s);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!tokenStore.access) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  async function copyText(text: string, okMsg: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMsg(okMsg);
    } catch {
      setMsg("复制失败，请手动复制");
    }
  }

  // ★ M6 保存海报：canvas 绘制邀请海报并下载 PNG
  function drawPoster() {
    const canvas = posterRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, "#0b1a33");
    grad.addColorStop(0.55, "#0e2440");
    grad.addColorStop(1, "#0a1428");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
    // 装饰圆环
    ctx.strokeStyle = "rgba(0,212,170,0.25)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(W - 60, 70, 110, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(50, H - 80, 80, 0, Math.PI * 2);
    ctx.stroke();
    // 标题
    ctx.fillStyle = "#00d4aa";
    ctx.font = "700 34px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("AI 信号聚合跟单", W / 2, 110);
    ctx.fillStyle = "#f1f5f9";
    ctx.font = "500 18px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText("好友注册即享 10% 返佣奖励", W / 2, 158);
    // 邀请码框
    ctx.fillStyle = "rgba(0,212,170,0.12)";
    ctx.strokeStyle = "#00d4aa";
    ctx.lineWidth = 2;
    const boxW = 300;
    const boxH = 96;
    const bx = (W - boxW) / 2;
    const by = 200;
    ctx.beginPath();
    ctx.roundRect(bx, by, boxW, boxH, 14);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#94a3b8";
    ctx.font = "400 14px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText("我的专属邀请码", W / 2, by + 32);
    ctx.fillStyle = "#00d4aa";
    ctx.font = "800 40px monospace";
    ctx.fillText(code || "······", W / 2, by + 74);
    // 说明
    ctx.fillStyle = "#94a3b8";
    ctx.font = "400 14px 'PingFang SC','Microsoft YaHei',sans-serif";
    ctx.fillText("注册时填写邀请码，好友购买套餐后您获得奖励", W / 2, H - 90);
    ctx.fillText("奖励核实期 24h · 风控场景 48h", W / 2, H - 62);
  }

  useEffect(() => {
    if (posterOpen) drawPoster();
  }, [posterOpen, code]);

  function savePoster() {
    const canvas = posterRef.current;
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `邀请海报-${code}.png`;
    a.click();
    setMsg("海报已保存");
  }

  const statCards: Array<[string, string, string]> = [
    ["累计邀请", `${stats?.total_invitees ?? 0}`, "人"],
    ["累计奖励", `${(stats?.total_reward ?? 0).toFixed(2)}`, "USDT"],
    ["待核实", `${(stats?.verifying_reward ?? 0).toFixed(2)}`, "USDT"],
    ["可提现", `${(stats?.available_reward ?? 0).toFixed(2)}`, "USDT"],
  ];

  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>邀请中心</div>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>好友购买套餐，您获得 10% 奖励 · 核实期 24h（风控 48h）</div>
        </div>

        {msg && <div style={{ background: "rgba(22,163,74,0.1)", border: "1px solid rgba(22,163,74,0.4)", color: "#4ade80", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{msg}</div>}
        {risk && <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: 6, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>风控提示：检测到批量试用购买，奖励核实期已延长至 48h</div>}

        {/* ★ M6 统计卡 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 20 }}>
          {statCards.map(([label, val, unit]) => (
            <div key={label} className="card" style={{ padding: 16 }}>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>
                {val} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--muted)" }}>{unit}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 8 }}>我的专属邀请码</div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ fontSize: 32, fontWeight: 800, letterSpacing: 6, color: "var(--accent)", fontFamily: "monospace" }}>{code || "······"}</div>
            <button className="btn btn-secondary" onClick={() => copyText(code, "邀请码已复制")}>复制</button>
          </div>
          {/* ★ M6 分享链接 */}
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--rule)" }}>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 8 }}>分享链接</div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input className="input" readOnly value={shareUrl} style={{ flex: 1, minWidth: 220, height: 38, fontSize: 12 }} />
              <button className="btn btn-secondary" onClick={() => copyText(shareUrl, "分享链接已复制")}>复制链接</button>
              <button className="btn btn-primary" onClick={() => setPosterOpen(true)}>生成海报</button>
            </div>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 12 }}>邀请记录（{invites.length}）</div>
          {invites.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>暂无邀请，分享邀请码给好友开始</div>
          ) : (
            invites.map((inv, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--rule)", fontSize: 13 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{inv.invitee_email}</div>
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>绑定于 {inv.bound_at?.slice(0, 10)}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontWeight: 700, color: "var(--success)" }}>+{inv.reward_usdt.toFixed(2)} USDT</div>
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>
                    {STATUS_LABEL[inv.reward_status] || inv.reward_status}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ★ M6 海报预览弹窗 */}
      {posterOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(7,14,26,0.85)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: 420, maxWidth: "92vw", background: "var(--surface-overlay)", border: "1px solid var(--rule)", borderRadius: 10, padding: 24, textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>邀请海报</div>
            <canvas ref={posterRef} width={600} height={800} style={{ width: "100%", height: "auto", borderRadius: 10, border: "1px solid var(--rule)" }} />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setPosterOpen(false)}>关闭</button>
              <button className="btn btn-primary" onClick={savePoster}>保存海报</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
