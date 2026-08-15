"""统一异常与错误码。"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类，携带 HTTP 状态码与错误码。"""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str = "", detail: dict[str, Any] | None = None):
        self.message = message or self.code
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}


# ── 认证 ──
class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"


# ── 参数/业务 ──
class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


# ── 交易所邀请码（★ G27）──
class ExchangeInviteError(AppError):
    """交易所邀请码核实失败：码不存在/已停用/已达上限/非本所码。"""

    status_code = 422
    code = "exchange_invite_invalid"


# ── API Key ──
class ApiKeyError(AppError):
    status_code = 422
    code = "api_key_invalid"


# ── 支付（★ G09）──
class PaymentError(AppError):
    status_code = 422
    code = "payment_error"


# ── 提现（★ G13）──
class WithdrawalError(AppError):
    status_code = 422
    code = "withdrawal_error"
