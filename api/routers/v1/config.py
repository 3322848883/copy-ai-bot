# v1/config 公开端点（免鉴权）：聚合前台展示所需平台规则
# 只暴露营销/规则性参数（邀请奖励、核实期、链上确认数、订单时限、提现参数、客服联系方式），
# 不包含 SMTP、密钥等任何敏感项。
from __future__ import annotations

from fastapi import APIRouter

from api.core.config import get_settings
from api.services.settings.service import get_chain_confirmations, get_rule, risk_rule_float

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def get_public_config() -> dict:
    s = get_settings()
    return {
        "referral": {
            "reward_pct": float(get_rule("referral_reward_pct") or 0),
            "verify_hours": int(get_rule("referral_verify_hours") or 0),
            "abuse_verify_hours": int(get_rule("referral_abuse_verify_hours") or 0),
        },
        "chain_confirmations": get_chain_confirmations(),
        "payment": {
            "order_ttl_min": int(get_rule("payment_order_ttl_min") or 30),
            "fee_tolerance_usdt": float(get_rule("payment_fee_tolerance_usdt") or 2.0),
        },
        "withdraw": {
            "min_withdrawal_usdt": risk_rule_float("min_withdrawal", float(s.withdraw_min_usdt)),
            "fee_usdt": risk_rule_float("withdrawal_fee", float(s.withdraw_fee_usdt)),
        },
        "support": {
            "email": str(get_rule("support_email") or ""),
            "telegram": str(get_rule("support_telegram") or ""),
        },
    }
