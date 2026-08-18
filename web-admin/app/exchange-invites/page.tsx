"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";
import { useToast } from "@/components/Toast";

type Code = { id: number; exchange: string; code: string; status: string; remark: string | null; bind_count: number; max_binds: number | null; created_at?: string | null };

const EXCHANGES = ["全部", "GATE", "BINANCE", "OKX", "BYBIT", "BITGET"];
const NET_CLASS: Record<string, string> = { gate: "gate", binance: "bin", okx: "okx", bybit: "byb", bitget: "bgt" };
const EX_LABEL: Record<string, string> = { gate: "GATE", binance: "BINANCE", okx: "OKX", bybit: "BYBIT", bitget: "BITGET" };

/** ★G27 交易所邀请码管理（对齐演示稿 exchange-invites：Tab + 列表 + 新增弹窗 + 审计）。 */
export default function AdminExchangeInvitesPage() {
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<Code[]>([]);
  const [ex, setEx] = useState("全部");

  // 新增弹窗
  const [showCreate, setShowCreate] = useState(false);
  const [newExchange, setNewExchange] = useState("gate");
  const [newCode, setNewCode] = useState("");
  const [newRemark, setNewRemark] = useState("");
  const [newMax, setNewMax] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: Code[] }>("/admin/v1/exchange-invites", {}, tokenStore.adminAccess);
      setItems(r.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/login");
      return;
    }
    load();
  }, [load, router]);

  const filtered = ex === "全部" ? items : items.filter((c) => (c.exchange || "").toUpperCase() === ex);

  async function create() {
    if (!newCode.trim()) {
      toast("warn", "请填写邀请码");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = { exchange: newExchange, code: newCode.trim(), remark: newRemark.trim() || null };
      if (newMax.trim()) {
        const n = Number(newMax.trim());
        if (!Number.isNaN(n) && n > 0) body.max_binds = n;
      }
      await apiFetch("/admin/v1/exchange-invites", { method: "POST", body: JSON.stringify(body) }, tokenStore.adminAccess);
      toast("success", `已新增邀请码 ${newCode.trim().toUpperCase()} · 审计留痕`);
      setShowCreate(false);
      setNewCode("");
      setNewRemark("");
      setNewMax("");
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(codeRow: Code) {
    try {
      await apiFetch(`/admin/v1/exchange-invites/${codeRow.id}/status`, { method: "PATCH", body: JSON.stringify({ status: codeRow.status === "active" ? "inactive" : "active" }) }, tokenStore.adminAccess);
      toast(codeRow.status === "active" ? "warn" : "success", codeRow.status === "active" ? `已停用 ${codeRow.code} · 新注册将拒绝此码` : `已启用 ${codeRow.code} · 恢复核实`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "操作失败");
    }
  }

  async function remove(codeRow: Code) {
    try {
      await apiFetch(`/admin/v1/exchange-invites/${codeRow.id}`, { method: "DELETE" }, tokenStore.adminAccess);
      toast("success", `已删除邀请码 ${codeRow.code} · 审计留痕`);
      load();
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "删除失败");
    }
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-hdr">
        <div>
          <div className="page-eyebrow">EXCHANGE INVITE CODES · ★G27</div>
          <h1 className="page-title">交易所邀请码<small>每所多码 · 注册核实 · 合作归属</small></h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ 新增邀请码</button>
        </div>
      </div>

      {/* 交易所 Tab */}
      <div className="ex-tabs">
        {EXCHANGES.map((e) => (
          <button key={e} className={`ex-tab${ex === e ? " active" : ""}`} onClick={() => setEx(e)}>{e}</button>
        ))}
      </div>

      {/* 邀请码列表 */}
      <div className="panel">
        <div className="panel-hdr">
          <div className="panel-title"><span className="sec-dot"></span>{ex === "全部" ? "全部邀请码" : `${ex} 邀请码列表`}</div>
          <span className="panel-sub">/admin/v1/exchange-invites · 用户注册时按此核实（G27）</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="ftx-table">
            <thead>
              <tr><th>邀请码</th><th>所属所</th><th>渠道备注</th><th className="num">已绑定</th><th className="num">绑定上限</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 && <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--muted)" }}>暂无邀请码</td></tr>}
              {filtered.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>{c.code}</td>
                  <td>
                    <span className="net-tag" style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 9, padding: "1px 8px", borderRadius: 2, border: "1px solid", color: "#00d4aa", borderColor: "rgba(0,212,170,0.4)" }}>{EX_LABEL[c.exchange] || c.exchange.toUpperCase()}</span>
                  </td>
                  <td className="sub-ref">{c.remark || "—"}</td>
                  <td className="num">{c.bind_count.toLocaleString()}</td>
                  <td className="num">{c.max_binds ? c.max_binds.toLocaleString() : "不限"}</td>
                  <td>{c.status === "active" ? <span className="badge badge-ok">启用</span> : <span className="badge badge-err">停用</span>}</td>
                  <td className="sub-ref">{c.created_at ? new Date(c.created_at).toLocaleDateString("zh-CN") : "—"}</td>
                  <td>
                    <button className={`btn btn-${c.status === "active" ? "secondary" : "primary"} btn-sm`} style={{ marginRight: 6 }} onClick={() => toggle(c)}>{c.status === "active" ? "停用" : "启用"}</button>
                    <button className="btn btn-secondary btn-sm" style={{ color: "#f87171" }} onClick={() => remove(c)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 16, padding: 12, borderRadius: 4, background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.25)", fontSize: 12, color: "var(--warning)" }}>
          ℹ 用户注册选所后必须填写对应交易所邀请码（G27 强制），后端调用 <span style={{ fontFamily: "var(--font-geist-mono), monospace" }}>verify_and_bind</span> 核实：码存在 + 启用 + 未达上限 + 属于所选所，任一不满足即拒绝并提示具体原因。
        </div>
      </div>

      {/* 新增邀请码弹窗 */}
      {showCreate && (
        <div className="modal-overlay" style={{ display: "flex" }} onClick={(e) => { if (e.target === e.currentTarget) setShowCreate(false); }}>
          <div className="modal">
            <div className="modal-hdr">
              <div className="modal-title">新增交易所邀请码</div>
              <button className="modal-close" onClick={() => setShowCreate(false)}>✕</button>
            </div>
            <div className="field">
              <label className="field-label">所属交易所</label>
              <select className="select" value={newExchange} onChange={(e) => setNewExchange(e.target.value)}>
                <option value="gate">Gate</option><option value="binance">Binance</option><option value="okx">OKX</option><option value="bybit">Bybit</option><option value="bitget">Bitget</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">邀请码</label>
              <input className="input input-mono" placeholder="如：5G8I2O" value={newCode} onChange={(e) => setNewCode(e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">渠道备注</label>
              <input className="input" placeholder="如：官网渠道 C" value={newRemark} onChange={(e) => setNewRemark(e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">绑定上限（留空 = 不限）</label>
              <input className="input input-mono" placeholder="如：1000" value={newMax} onChange={(e) => setNewMax(e.target.value)} />
            </div>
            <div className="warn-note">
              <span>⚠</span>
              <span>新增后即进入核实池，用户注册填此码将绑定合作归属；启停用与上限变更均写 audit-log</span>
            </div>
            <div className="modal-btn-row">
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowCreate(false)}>取消</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={create} disabled={busy || !newCode.trim()}>{busy ? "创建中…" : "确认新增"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
