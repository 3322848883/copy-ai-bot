import * as S from "@/components/authStyles";

/** 认证页左侧品牌区（登录 / 注册共用）：logo + 大标题 + 4 条特性 + 信号波。
 *  对齐设计稿 .brand-panel；<900px 时由调用方控制隐藏（visible=false）。 */
export default function AuthBrand({ visible }: { visible: boolean }) {
  return (
    <div style={{ ...S.brandPanel, display: visible ? "flex" : "none" }}>
      <div style={S.brandLogo}>
        <div style={S.brandMark}>
          <svg viewBox="0 0 16 16" fill="none" width={22} height={22}>
            <path d="M1 9h3l2-6 3 10 2-5h4" stroke="#06281f" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        signal·saas
      </div>
      <div style={S.brandHero}>
        跨 5 大交易所
        <br />
        <span style={{ color: "var(--accent)" }}>信号聚合</span>，一键跟单
      </div>
      <div style={S.brandFeats}>
        {[
          ["▤", "聚合 Binance · OKX · Bybit · Bitget · Gate 带单信号"],
          ["▣", "独立跟单机器人 · 自动执行开仓/加仓/减仓/平仓"],
          ["⇄", "邀请好友 · 订阅费 10% 现金奖励"],
          ["◎", "资金 100% 在你自己的交易所账户"],
        ].map(([ic, txt]) => (
          <div key={txt} style={S.featRow}>
            <span style={S.featIc}>{ic}</span> {txt}
          </div>
        ))}
      </div>
      <div style={S.brandWave}>
        <svg viewBox="0 0 500 70" preserveAspectRatio="none" width="100%" height="100%">
          <path
            d="M0,50 C80,30 130,60 210,42 C290,24 340,58 420,36 C460,24 480,36 500,28"
            fill="none" stroke="rgba(0,212,170,0.3)" strokeWidth={1.5} strokeDasharray="4 6"
          />
          <path
            d="M0,38 C100,22 180,48 270,30 C360,12 430,40 500,20"
            fill="none" stroke="var(--accent)" strokeWidth={2}
            style={{ filter: "drop-shadow(0 0 8px rgba(0,212,170,0.5))" }}
          />
        </svg>
      </div>
    </div>
  );
}
