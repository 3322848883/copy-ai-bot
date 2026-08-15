# USDT 本位换算 4 步法（M3 T3.4，★ G08 合约级 ContractSpec）
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from api.core.errors import ValidationError


@dataclass
class Contract:
    """合约规格（★ G08：从 ContractSpec 表按 exchange+symbol 查询）。"""

    exchange: str
    symbol: str
    face_value_usdt: float
    min_size: float
    size_precision: int  # 小数位


@dataclass
class SizeIntent:
    qty: float
    margin_usdt: float
    notional_usdt: float
    min_size_bumped: bool = False  # ★ 向上补足标记


class PositionSizer:
    """USDT 本位换算 4 步法（设计蓝本 §6.4 + 开发计划 §4.3）。"""

    def __init__(self, contract: Contract) -> None:
        self.contract = contract

    def compute(
        self,
        *,
        amount_mode: str,          # fixed / percent
        fixed_amount_usdt: float | None,
        percent: float | None,
        account_free_usdt: float,
        leverage: int,
    ) -> SizeIntent:
        """计算下单数量与保证金。

        Step1 target_notional_usdt = fixed 或 percent × free
        Step2 face = contract.face_value_usdt
        Step3 qty_raw = target / face
              qty_raw < min_size → qty = min_size（向上补足）
              否则 → floor(qty_raw, decimals=size_precision)（向下取整）
        Step4 margin = qty × face / leverage
              margin > free → 拒绝（InsufficientBalance）
        """
        if leverage <= 0:
            raise ValidationError("leverage 必须为正")

        # Step1: 目标名义价值
        if amount_mode == "fixed":
            target = fixed_amount_usdt if fixed_amount_usdt is not None else 0.0
        elif amount_mode == "percent":
            target = account_free_usdt * (percent or 0) / 100.0
        else:
            raise ValidationError(f"amount_mode 非法: {amount_mode}")
        if target <= 0:
            raise ValidationError("目标名义价值必须 > 0")

        # Step2/3: 数量换算（★ G08 合约级参数）
        face = Decimal(str(self.contract.face_value_usdt))
        if face <= 0:
            raise ValidationError("合约面值必须 > 0")
        qty_raw = Decimal(str(target)) / face
        min_size = Decimal(str(self.contract.min_size))

        bumped = False
        if qty_raw < min_size:
            qty = min_size  # 向上补足
            bumped = True
        else:
            precision = Decimal(10) ** -self.contract.size_precision
            qty = qty_raw.quantize(precision, rounding=ROUND_FLOOR)  # 向下取整

        # Step4: 保证金校验
        qty_f = float(qty)
        margin = qty_f * float(face) / leverage
        if margin > account_free_usdt + 1e-9:
            raise InsufficientBalance(
                qty=qty_f,
                margin=margin,
                free=account_free_usdt,
            )
        return SizeIntent(
            qty=qty_f,
            margin_usdt=margin,
            notional_usdt=qty_f * float(face),
            min_size_bumped=bumped,
        )


class InsufficientBalance(ValidationError):
    """保证金不足。"""

    code = "insufficient_balance"

    def __init__(self, qty: float, margin: float, free: float):
        self.qty = qty
        self.margin = margin
        self.free = free
        super().__init__(f"保证金不足: 需 {margin:.2f} USDT，可用 {free:.2f} USDT")
