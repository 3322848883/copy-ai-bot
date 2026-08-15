"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, tokenStore } from "@/lib/api";

type Code = { id: number; exchange: string; code: string; status: string; remark: string | null; bind_count: number; max_binds: number | null };

/** M5 T5.3 邀请码管理：★G27 交易所邀请码 CRUD + 绑定计数。 */
export default function AdminInvitesPage() {
  const router = useRouter();
  const [items, setItems] = useState<Code[]>([]);
  const [exchange, setExchange] = useState("");
  const [code, setCode] = useState("");
  const [remark, setRemark] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ items: Code[] }>("/admin/v1/exchange-invites", {}, tokenStore.adminAccess);
      setItems(r.items);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!tokenStore.adminAccess) {
      router.push("/admin/login");
      return;
    }
    load();
  }, [load, router]);

  async function create() {
    try {
      await apiFetch("/admin/v1/exchange-invites", { method: "POST", body: JSON.stringify({ exchange, code, remark }) }, tokenStore.adminAccess);
      setMsg("邀请码已创建");
      setCode("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "创建失败");
    }
  }

  async function toggle(codeRow: Code) {
    try {
      await apiFetch(`/admin/v1/exchange-invites/${codeRow.id}/status`, { method: "PATCH", body: JSON.stringify({ status: codeRow.status === "active" ? "inactive" : "active" }) }, tokenStore.adminAccess);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function remove(codeRow: Code) {
    try {
      await apiFetch(`/admin/v1/exchange-invites/${codeRow.id}`, { method: "DELETE" }, tokenStore.adminAccess);
      setMsg("已删除");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "删除失败");
    }
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>邀请码管理（★G27）</div>
      {msg && <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 12 }}>{msg}</div>}
      <div className="card" style={{ marginBottom: 16, display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
        <div>
          <label className="label">交易所</label>
          <select className="input" value={exchange} onChange={(e) => setExchange(e.target.value)}>
            <option value="gate">gate</option><option value="binance">binance</option><option value="okx">okx</option><option value="bybit">bybit</option><option value="bitget">bitget</option>
          </select>
        </div>
        <div>
          <label className="label">邀请码</label>
          <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="如 8F3K2A" />
        </div>
        <div>
          <label className="label">备注</label>
          <input className="input" value={remark} onChange={(e) => setRemark(e.target.value)} />
        </div>
        <button className="btn btn-primary" onClick={create} disabled={!exchange || !code}>创建</button>
      </div>
      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left" }}>
              <th style={th}>交易所</th><th style={th}>邀请码</th><th style={th}>状态</th><th style={th}>绑定数/上限</th><th style={th}>备注</th><th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} style={{ borderTop: "1px solid var(--rule)" }}>
                <td style={{ ...td, fontWeight: 600 }}>{c.exchange}</td>
                <td style={{ ...td, fontFamily: "monospace" }}>{c.code}</td>
                <td style={td}>{c.status === "active" ? <span style={{ color: "var(--success)" }}>启用</span> : <span style={{ color: "var(--muted)" }}>停用</span>}</td>
                <td style={td}>{c.bind_count} / {c.max_binds ?? "∞"}</td>
                <td style={td}>{c.remark || "-"}</td>
                <td style={td}>
                  <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12, marginRight: 6 }} onClick={() => toggle(c)}>{c.status === "active" ? "停用" : "启用"}</button>
                  <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12, color: "var(--danger)" }} onClick={() => remove(c)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid var(--rule)", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "10px", whiteSpace: "nowrap" };
