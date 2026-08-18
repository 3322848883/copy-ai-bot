"use client";

import { useState } from "react";

type Confirmations = { trc20: number; bep20: number; erc20: number; aptos: number };

const NETWORK_INFO = [
  { key: "trc20", label: "TRC-20", conf: 12, eta: "约 1 分钟", fee: "低", tip: "波场网络，交易所普遍支持，小额首选" },
  { key: "bep20", label: "BEP-20", conf: 15, eta: "约 1 分钟", fee: "低", tip: "BSC 网络，速度快费用低，推荐" },
  { key: "erc20", label: "ERC-20", conf: 32, eta: "约 7 分钟", fee: "较高", tip: "以太坊主网，小额支付不建议选用" },
  { key: "aptos", label: "APTOS", conf: 20, eta: "约 30 秒", fee: "极低", tip: "速度最快费用最低，钱包支持较少" },
];

const stepsOf = (ttlMin: number) => [
  {
    title: "选择套餐与网络",
    body: (
      <>
        <p>选择要订阅的套餐，再选择付款网络。四条网络均支持自动核验，建议优先选择 <b>TRC-20 / BEP-20 / APTOS</b>（速度快、费用低）；ERC-20（以太坊主网）手续费较高且确认较慢，小额支付不建议选用。</p>
      </>
    ),
  },
  {
    title: "复制收款地址",
    body: (
      <>
        <p>点击「创建支付订单」后，订单卡会展示该网络的平台收款地址，点击「复制地址」。</p>
        <p className="pg-warn">⚠ BEP-20 与 ERC-20 共用同一个地址（0x 开头），但<b>两条网络互不通用</b>——转账时选错网络，资产将无法找回。请务必在钱包/交易所中选择与订单一致的网络。</p>
      </>
    ),
  },
  {
    title: "完成转账",
    body: (
      <>
        <p><b>从交易所提现：</b>提币网络选择与订单一致的网络，粘贴收款地址。提现手续费由交易所按其费率从提现金额中扣除（不同交易所、不同网络费率不同，以提现页面显示为准）。为避免到账金额不足，建议提现时<b>适当多留一些缓冲</b>。</p>
        <p><b>从钱包直转：</b>网络费（TRX / BNB / ETH / APT）由钱包另行扣除，USDT 会全额到账。</p>
        <p className="pg-ok">✓ 实际到账金额略高于订单金额没有关系，套餐正常开通，多付部分会记录在订单详情中。</p>
      </>
    ),
  },
  {
    title: "提交交易哈希 TxHash",
    body: (
      <>
        <p>转账完成后，回到本页，在「交易哈希 TxHash」输入框中粘贴这笔转账的哈希，点击「提交并验证」。</p>
        <p><b>哪里找 TxHash：</b>钱包的转账记录详情里叫「交易哈希 / 交易 ID / TxID」；交易所的提现记录里叫「交易 ID / 哈希」。TRC-20 与 Aptos 是 64 位十六进制字符串（Aptos 可带 0x 前缀），BEP-20 / ERC-20 是 0x 开头的 66 位字符串。</p>
        <p className="pg-warn">⚠ 必须提交 TxHash 系统才能核验入账，仅转账不提交无法自动开通。</p>
      </>
    ),
  },
  {
    title: "等待链上确认",
    body: (
      <>
        <p>提交后系统自动校验（收款地址、金额、交易状态）并跟踪链上确认数，达到要求后自动开通订阅、发送邮件通知，全程无需重复提交。</p>
        <p>订单有效期 {ttlMin} 分钟（以订单卡倒计时为准）。超时未完成可重新下单；如遇链上拥堵导致确认缓慢，订单会自动轮询，请耐心等待。</p>
      </>
    ),
  },
];

const FAQ = [
  {
    q: "转多了 / 到账金额超过订单金额怎么办？",
    a: "不影响开通。系统按实际到账核验，多付部分会记录在订单的实际到账金额中；如需处理超额部分，请联系客服。",
  },
  {
    q: "提示「该交易早于订单创建时间超过 15 分钟」？",
    a: "为防止盗用他人链上付款记录，系统只接受订单创建前 15 分钟之后的转账。请重新创建订单，转账完成后再提交 TxHash（先下单、后转账的顺序永远不会触发此提示）。",
  },
  {
    q: "提示「该 TxHash 已被其他订单使用」？",
    a: "一笔链上转账只能激活一个订单。如需再次订阅，请创建新订单并完成新的转账。",
  },
  {
    q: "一直显示「确认中」？",
    a: "链上拥堵时确认会变慢，系统每 2 分钟自动轮询，无需重复提交。若长时间（30 分钟以上）无进展，可联系客服人工核实。",
  },
  {
    q: "转错网络 / 转错地址了怎么办？",
    a: "请立即联系客服。链上转账不可逆，跨网络转入的资产可能无法找回，转账前务必核对网络与地址。",
  },
];

export default function PaymentGuideModal({
  open,
  onClose,
  network,
  confirmations,
  ttlMin,
  supportEmail,
}: {
  open: boolean;
  onClose: () => void;
  network?: string;
  confirmations?: Confirmations;
  ttlMin?: number;
  supportEmail?: string;
}) {
  const [tab, setTab] = useState<"steps" | "nets" | "faq">("steps");
  const [faqOpen, setFaqOpen] = useState<number | null>(0);

  if (!open) return null;
  // 确认数以后台配置（props）为准，接口未返回时用默认值兜底
  const ttl = ttlMin ?? 30;
  const STEPS = stepsOf(ttl);
  const nets = NETWORK_INFO.map((n) => ({ ...n, conf: confirmations?.[n.key as keyof Confirmations] ?? n.conf }));
  const cur = nets.find((n) => n.key === network);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(4,10,20,0.72)", backdropFilter: "blur(4px)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: "var(--panel, #0f1a30)", border: "1px solid var(--rule)", borderRadius: 14, width: "100%", maxWidth: 760, maxHeight: "86vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 24px 80px rgba(0,0,0,0.5)" }}
      >
        {/* 头部 */}
        <div style={{ padding: "18px 22px 0", borderBottom: "1px solid var(--rule)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 10, fontFamily: "var(--font-geist-mono), monospace", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--accent)", marginBottom: 4 }}>
                HOW TO PAY
              </div>
              <div style={{ fontWeight: 700, fontSize: 17 }}>USDT 支付教程</div>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, color: "var(--muted)", cursor: "pointer", lineHeight: 1, padding: 4 }}>✕</button>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {([
              ["steps", "支付流程"],
              ["nets", "网络对比"],
              ["faq", "常见问题"],
            ] as const).map(([k, label]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                style={{
                  flex: 1, height: 38, borderTopLeftRadius: 8, borderTopRightRadius: 8, cursor: "pointer",
                  border: "none", borderBottom: tab === k ? "2px solid var(--accent)" : "2px solid transparent",
                  background: tab === k ? "var(--accent-soft)" : "transparent",
                  color: tab === k ? "var(--accent)" : "var(--muted)",
                  fontSize: 13, fontWeight: tab === k ? 600 : 400, transition: "all .15s",
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* 内容 */}
        <div style={{ overflow: "auto", padding: "20px 22px 24px", fontSize: 13, lineHeight: 1.75, color: "var(--fg)" }}>
          {tab === "steps" && (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {STEPS.map((s, i) => (
                <div key={i} style={{ display: "flex", gap: 14 }}>
                  {/* 步骤序号列 */}
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                    <div style={{
                      width: 26, height: 26, borderRadius: "50%", display: "grid", placeItems: "center",
                      background: "var(--accent-soft)", border: "1px solid var(--accent)",
                      color: "var(--accent)", fontFamily: "var(--font-geist-mono), monospace", fontSize: 12, fontWeight: 700,
                    }}>
                      {i + 1}
                    </div>
                    {i < STEPS.length - 1 && <div style={{ width: 1, flex: 1, background: "var(--rule)", minHeight: 20, margin: "4px 0" }} />}
                  </div>
                  {/* 步骤内容 */}
                  <div style={{ paddingBottom: i < STEPS.length - 1 ? 22 : 0, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 14 }}>{s.title}</div>
                    <div className="pg-body">{s.body}</div>
                  </div>
                </div>
              ))}
              {cur && (
                <div style={{ marginTop: 8, padding: "10px 14px", borderRadius: 8, border: "1px solid rgba(0,212,170,0.35)", background: "rgba(0,212,170,0.06)", fontSize: 12 }}>
                  当前订单网络 <b style={{ color: "var(--accent)" }}>{cur.label}</b>：{cur.tip}，需 {cur.conf} 个确认，预计 {cur.eta} 完成确认。
                </div>
              )}
            </div>
          )}

          {tab === "nets" && (
            <div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, tableLayout: "fixed" }}>
                <colgroup>
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "12%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "42%" }} />
                </colgroup>
                <thead>
                  <tr style={{ color: "var(--muted)", textAlign: "left" }}>
                    <th style={{ padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}>网络</th>
                    <th style={{ padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}>确认数</th>
                    <th style={{ padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}>预计确认时长</th>
                    <th style={{ padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}>手续费水平</th>
                    <th style={{ padding: "10px 8px", borderBottom: "1px solid var(--rule)" }}>建议</th>
                  </tr>
                </thead>
                <tbody>
                  {nets.map((n) => (
                    <tr key={n.key} style={{ borderBottom: "1px solid var(--rule)" }}>
                      <td style={{ padding: "10px 8px", fontWeight: 600 }}>{n.label}</td>
                      <td style={{ padding: "10px 8px", fontFamily: "var(--font-geist-mono), monospace" }}>{n.conf} 块</td>
                      <td style={{ padding: "10px 8px" }}>{n.eta}</td>
                      <td style={{ padding: "10px 8px", color: n.fee === "较高" ? "var(--warning)" : "var(--success)" }}>{n.fee}</td>
                      <td style={{ padding: "10px 8px", color: "var(--muted)", fontSize: 12 }}>{n.tip}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p style={{ marginTop: 14, color: "var(--muted)", fontSize: 12 }}>
                确认数为系统要求的安全阈值；手续费水平指该网络上 USDT 转账的链上成本相对水平，实际费用以钱包/交易所显示为准。
              </p>
            </div>
          )}

          {tab === "faq" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {FAQ.map((f, i) => (
                <div key={i} style={{ border: "1px solid var(--rule)", borderRadius: 8, overflow: "hidden" }}>
                  <button
                    onClick={() => setFaqOpen(faqOpen === i ? null : i)}
                    style={{
                      width: "100%", textAlign: "left", padding: "12px 14px", cursor: "pointer",
                      background: faqOpen === i ? "var(--surface-overlay, #162038)" : "transparent",
                      border: "none", color: "var(--fg)", fontSize: 13, fontWeight: 600,
                      display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
                    }}
                  >
                    <span>{f.q}</span>
                    <span style={{ color: "var(--muted)", fontSize: 12, transform: faqOpen === i ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform .2s", display: "inline-block" }}>▾</span>
                  </button>
                  {faqOpen === i && (
                    <div style={{ padding: "0 14px 12px", color: "var(--muted)", fontSize: 12.5, lineHeight: 1.8, borderTop: "1px solid var(--rule)", paddingTop: 10 }}>
                      {f.a}
                    </div>
                  )}
                </div>
              ))}
              {supportEmail && (
                <div style={{ marginTop: 4, padding: "10px 14px", borderRadius: 8, border: "1px solid rgba(0,212,170,0.3)", background: "rgba(0,212,170,0.05)", fontSize: 12, color: "var(--muted)" }}>
                  人工协助邮箱：
                  <a href={`mailto:${supportEmail}`} style={{ color: "var(--accent)", textDecoration: "none" }}>{supportEmail}</a>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
