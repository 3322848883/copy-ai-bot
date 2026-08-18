# 平台设置服务（后台「系统设置」：验证码/模板/套餐/邀请/链上确认 集中可配置）
# 存储：Redis（sys:setting:* / sys:template:* / sys:plans），Redis 不可用时降级默认值
from __future__ import annotations

import json

from api.core.config import get_settings


def _smtp_defaults() -> dict:
    """SMTP 规则兜底默认值 = 当前环境变量配置（后台未覆盖时沿用 .env）。"""
    s = get_settings()
    return {
        "smtp_host": s.smtp_host,
        "smtp_port": s.smtp_port,
        "smtp_user": s.smtp_user or "",
        "smtp_password": s.smtp_password or "",
        "mail_from": s.mail_from,
    }


_SMTP_DEFAULTS = _smtp_defaults()


# ── 平台参数定义（与 admin/risk 的 RISK_RULES 同模式，默认值兜底）──
PLATFORM_RULES: dict[str, dict] = {
    # 验证码（注册邮箱验证码）
    "verify_code_enabled": {"default": True, "label": "注册邮箱验证码", "group": "验证码", "bool": True},
    "verify_code_ttl_min": {"default": 5, "label": "验证码有效期", "unit": "min", "group": "验证码"},
    "verify_code_max_attempts": {"default": 5, "label": "最大错误尝试", "unit": "次", "group": "验证码"},
    "verify_code_dev_code": {"default": "123456", "label": "dev 固定验证码", "unit": "", "group": "验证码", "str": True},
    "verify_code_length": {"default": 6, "label": "验证码位数", "unit": "位", "group": "验证码"},
    # 邀请奖励
    "referral_reward_pct": {"default": 10.0, "label": "邀请奖励比例", "unit": "%", "group": "邀请奖励"},
    "referral_verify_hours": {"default": 24, "label": "邀请核实期", "unit": "h", "group": "邀请奖励"},
    "referral_abuse_trial_threshold": {"default": 3, "label": "刷单检测·试用订单阈值", "unit": "笔/h", "group": "邀请奖励"},
    "referral_abuse_verify_hours": {"default": 48, "label": "风控延长核实期", "unit": "h", "group": "邀请奖励"},
    # 链上确认数
    "chain_confirm_trc20": {"default": 12, "label": "TRC-20 确认数", "unit": "块", "group": "链上确认"},
    "chain_confirm_bep20": {"default": 15, "label": "BEP-20 确认数", "unit": "块", "group": "链上确认"},
    "chain_confirm_erc20": {"default": 32, "label": "ERC-20 确认数", "unit": "块", "group": "链上确认"},
    "chain_confirm_aptos": {"default": 20, "label": "APTOS 确认数", "unit": "块", "group": "链上确认"},
    # 支付订单
    "payment_order_ttl_min": {"default": 30, "label": "支付订单倒计时", "unit": "min", "group": "支付订单"},
    # 邮件
    "mail_enabled": {"default": True, "label": "邮件发送", "unit": "", "group": "邮件", "bool": True},
    "smtp_host": {"default": _SMTP_DEFAULTS["smtp_host"], "label": "SMTP 主机", "unit": "", "group": "邮件", "str": True},
    "smtp_port": {"default": _SMTP_DEFAULTS["smtp_port"], "label": "SMTP 端口", "unit": "", "group": "邮件"},
    "smtp_user": {"default": _SMTP_DEFAULTS["smtp_user"], "label": "SMTP 账号", "unit": "", "group": "邮件", "str": True},
    "smtp_password": {"default": _SMTP_DEFAULTS["smtp_password"], "label": "SMTP 密码", "unit": "", "group": "邮件", "str": True, "secret": True},
    "mail_from": {"default": _SMTP_DEFAULTS["mail_from"], "label": "发件人地址", "unit": "", "group": "邮件", "str": True},
}

# 密钥型规则：读取回显脱敏（用占位掩码），留空 / 占位符保存时保留原值
_SECRET_KEYS: frozenset[str] = frozenset({"smtp_password"})
_SECRET_MASK = "********"

# 邮件模板（可后台编辑，Redis 覆盖默认值）
TEMPLATE_SUBJECTS: dict[str, str] = {
    "verify_code": "邮箱验证码",
    "subscription_expiring": "订阅即将到期",
}
DEFAULT_TEMPLATES: dict[str, str] = {
    "verify_code": (
        '<div style="border-bottom:1px solid #22304a;padding-bottom:16px;margin-bottom:20px">'
        '<strong style="color:#00d4aa;font-size:18px">signal·saas</strong>'
        '<span style="color:#64748b;font-size:12px;margin-left:8px">信号聚合跟单平台</span></div>'
        '<h2 style="color:#f1f5f9;font-size:18px;margin:0 0 12px">邮箱验证码</h2>'
        '<p style="color:#94a3b8;font-size:14px;line-height:1.6;margin:0 0 20px">'
        '您正在使用该邮箱注册 / 登录，本次验证码为：</p>'
        '<div style="font-size:34px;font-weight:700;letter-spacing:10px;color:#40ffc5;'
        'background:#0a1628;border:1px dashed #00d4aa;border-radius:10px;padding:18px;'
        'text-align:center;margin:0 0 20px">{code}</div>'
        '<p style="color:#94a3b8;font-size:13px;line-height:1.7;margin:0 0 8px">'
        '验证码 <strong style="color:#40ffc5">{ttl} 分钟</strong>内有效，请勿转发或泄露给他人。</p>'
        '<p style="color:#64748b;font-size:12px;line-height:1.7;margin:0">'
        '若非本人操作，请忽略本邮件，并留意账号安全。</p>'
        '<div style="border-top:1px solid #22304a;margin-top:24px;padding-top:12px">'
        '<p style="color:#475569;font-size:11px;margin:0">本邮件由系统自动发送，请勿直接回复。</p></div>'
    ),
    "subscription_expiring": (
        '<div style="border-bottom:1px solid #22304a;padding-bottom:16px;margin-bottom:20px">'
        '<strong style="color:#00d4aa;font-size:18px">signal·saas</strong>'
        '<span style="color:#64748b;font-size:12px;margin-left:8px">信号聚合跟单平台</span></div>'
        '<h2 style="color:#f59e0b;font-size:18px;margin:0 0 12px">订阅即将到期</h2>'
        '<p style="color:#f1f5f9;font-size:14px;line-height:1.7;margin:0 0 16px">'
        '您好 <strong style="color:#40ffc5">{name}</strong>，您的订阅将于 '
        '<strong style="color:#40ffc5">{expires}</strong> 到期。</p>'
        '<div style="background:#0a1628;border:1px solid #334155;border-radius:8px;padding:14px 16px;margin:0 0 16px">'
        '<p style="color:#94a3b8;font-size:13px;line-height:1.7;margin:0">'
        '到期后将暂停开仓 / 加仓，持仓与配置保留；续费后立即恢复交易。</p></div>'
        '<p style="color:#64748b;font-size:12px;line-height:1.7;margin:0">请及时前往「充值订阅」续费，避免影响跟单。</p>'
        '<div style="border-top:1px solid #22304a;margin-top:24px;padding-top:12px">'
        '<p style="color:#475569;font-size:11px;margin:0">本邮件由系统自动发送，请勿直接回复。</p></div>'
    ),
}

# 默认套餐（后台可增删改，Redis sys:plans；仅保留原硬编码为兜底）
DEFAULT_PLANS: list[dict] = [
    {
        "plan_id": "trial_5u",
        "name": "试用套餐",
        "price_usdt": 5.0,
        "duration_days": 7,
        "trial": True,
        "max_purchase": 1,
        "enabled": True,
    },
    {
        "plan_id": "monthly_19_9u",
        "name": "正式套餐",
        "price_usdt": 19.9,
        "duration_days": 30,
        "trial": False,
        "max_purchase": None,
        "enabled": True,
    },
]


def _redis():
    from redis import Redis

    return Redis.from_url(get_settings().redis_url, decode_responses=True)


# ── 平台参数 ──
def get_rule(key: str):
    """读取平台参数（Redis 优先，默认值兜底）。"""
    meta = PLATFORM_RULES.get(key)
    if meta is None:
        return None
    try:
        r = _redis()
        raw = r.get(f"sys:setting:{key}")
    except Exception:  # noqa: BLE001 Redis 不可用降级默认
        raw = None
    if raw is None:
        return meta["default"]
    if meta.get("bool"):
        return raw == "1"
    if meta.get("str"):
        return raw
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def set_rule(key: str, value) -> None:
    """写入平台参数。密钥型规则留空 / 占位掩码时不覆盖（保留原值）。"""
    meta = PLATFORM_RULES.get(key)
    if meta is None:
        raise ValueError(f"未知设置项: {key}")
    if key in _SECRET_KEYS and (value in (None, "") or str(value) == _SECRET_MASK):
        return
    r = _redis()
    if meta.get("bool"):
        r.set(f"sys:setting:{key}", "1" if value else "0")
    else:
        r.set(f"sys:setting:{key}", str(value))


def get_all_rules() -> dict:
    out = {}
    for key in PLATFORM_RULES:
        val = get_rule(key)
        if key in _SECRET_KEYS:
            out[key] = _SECRET_MASK if val else ""
        else:
            out[key] = val
    return out


# ── 邮件模板 ──
def get_template(key: str) -> tuple[str, str]:
    """返回 (subject, html)。Redis 覆盖默认值。"""
    subject = TEMPLATE_SUBJECTS.get(key, "")
    html = DEFAULT_TEMPLATES.get(key, "")
    try:
        r = _redis()
        raw = r.get(f"sys:template:{key}")
    except Exception:  # noqa: BLE001
        raw = None
    if raw:
        try:
            data = json.loads(raw)
            subject = data.get("subject", subject)
            html = data.get("html", html)
        except (ValueError, TypeError):
            html = raw
    return subject, html


def set_template(key: str, subject: str, html: str) -> None:
    r = _redis()
    r.set(f"sys:template:{key}", json.dumps({"subject": subject, "html": html}))


# ── 订阅套餐 ──
def get_plans() -> list[dict]:
    """读取套餐列表（Redis 优先，默认值兜底）。"""
    try:
        r = _redis()
        raw = r.get("sys:plans")
    except Exception:  # noqa: BLE001
        raw = None
    if raw:
        try:
            plans = json.loads(raw)
            if isinstance(plans, list) and plans:
                return plans
        except (ValueError, TypeError):
            pass
    return [dict(p) for p in DEFAULT_PLANS]


def save_plans(plans: list[dict]) -> None:
    r = _redis()
    r.set("sys:plans", json.dumps(plans))


def get_plan(plan_id: str) -> dict | None:
    for p in get_plans():
        if p.get("plan_id") == plan_id:
            return p
    return None


# ── 链上确认数 ──
def get_chain_confirmations() -> dict[str, int]:
    return {
        "trc20": int(get_rule("chain_confirm_trc20")),
        "bep20": int(get_rule("chain_confirm_bep20")),
        "erc20": int(get_rule("chain_confirm_erc20")),
        "aptos": int(get_rule("chain_confirm_aptos")),
    }


# ── 风控规则（admin/risk 的 RISK_RULES 存于 risk:rule:*，供提现/风控引擎读取）──
def get_risk_rule(key: str, default):
    """读取后台「风控中心」配置项（risk:rule:{key}），未设置/不可用返回 default。"""
    try:
        r = _redis()
        raw = r.get(f"risk:rule:{key}")
    except Exception:  # noqa: BLE001 Redis 不可用降级默认
        raw = None
    if raw is None:
        return default
    return raw


def risk_rule_float(key: str, default: float) -> float:
    """读取风控规则并转 float。"""
    try:
        return float(get_risk_rule(key, default))
    except (TypeError, ValueError):
        return default