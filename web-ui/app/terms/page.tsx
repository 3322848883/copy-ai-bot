"use client";

import Link from "next/link";

/** 服务条款（合规 M6 T6.1；上线前需外部法务复核）。 */
export default function TermsPage() {
  return (
    <main style={{ minHeight: "100vh", position: "relative" }}>
      <div className="aurora" />
      <div className="grid-bg" />
      <div style={{ maxWidth: 820, margin: "0 auto", padding: "48px 24px", position: "relative", zIndex: 1 }}>
        <Link href="/" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>← 返回首页</Link>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: "16px 0 8px" }}>服务条款</h1>
        <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 24 }}>更新日期：2026-08-15</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20, fontSize: 14, lineHeight: 1.8 }}>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>1. 服务性质</h2>
            <p style={{ color: "var(--muted)" }}>
              本平台为信号聚合与跟单工具，向您提供跨交易所信号订阅与自动化跟单执行服务。平台不生产信号、不做自营、不抽水不返佣，唯一收入为订阅费。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>2. 风险自担声明</h2>
            <p style={{ color: "var(--muted)" }}>
              数字资产交易（含合约杠杆交易）具有极高风险，可能导致全部本金损失。跟单信号不构成任何投资建议。您应充分理解风险，并根据自身风险承受能力独立决策；因市场波动、信号延迟、交易所故障等造成的损失由您自行承担。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>3. 订阅与退款</h2>
            <p style={{ color: "var(--muted)" }}>
              订阅按周期付费（试用/正式套餐）。试用套餐每账号限购一次。数字内容与服务订阅一经确认并开通，原则上不退款；如因平台原因无法提供服务，可申请按剩余周期比例退款。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>4. 合规红线</h2>
            <p style={{ color: "var(--muted)" }}>
              禁止使用本平台进行洗钱、刷单、操纵市场或任何违反法律法规的活动。平台有权对可疑账号冻结并配合监管调查。
            </p>
          </section>
          <section>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>5. 免责条款</h2>
            <p style={{ color: "var(--muted)" }}>
              因不可抗力（网络中断、交易所 API 变更、链上拥堵、监管政策变化等）导致的延迟、中断或损失，平台在法律法规允许范围内不承担责任。
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
