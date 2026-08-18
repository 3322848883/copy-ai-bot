import * as S from "@/components/authStyles";
import { BrandMark, BrandName } from "@/components/Brand";

/** 认证页左侧品牌区（登录 / 注册共用）：logo + 大标题 + 4 条特性 + 信号波。
 *  对齐设计稿 .brand-panel；<900px 时由调用方控制隐藏（visible=false）。 */
export default function AuthBrand({ visible }: { visible: boolean }) {
  return (
    <div style={{ ...S.brandPanel, display: visible ? "flex" : "none" }}>
      <div style={S.brandLogo}>
        <BrandMark size={34} />
        <BrandName size={20} />
      </div>
      <div style={S.brandHero}>
        你睡觉时，
        <br />
        <span style={{ color: "var(--accent)" }}>AI</span> 仍在为你捕获 Alpha
      </div>
      <div style={S.brandFeats}>
        {[
          ["◈", "AI 智能引擎 7×24 扫描全市场，信号识别持续进化"],
          ["▣", "全自动跟单执行，开仓 / 加仓 / 减仓 / 平仓秒级同步"],
          ["⇄", "邀请好友即享订阅费 10% 现金奖励，无上限"],
          ["◎", "资金 100% 留在你自己的账户，随时掌控"],
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
