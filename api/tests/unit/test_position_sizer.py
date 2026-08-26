from __future__ import annotations

import pytest

from api.services.copyengine.sizer import Contract, PositionSizer


def test_fixed_amount_is_order_margin_and_leverage_expands_notional():
    """固定 5 USDT、10x = 约 5 USDT 保证金、50 USDT 名义仓位。"""
    sizer = PositionSizer(
        Contract(
            exchange="gate",
            symbol="MSTRXUSDT",
            face_value_usdt=0.01,
            min_size=1,
            size_precision=0,
        )
    )

    intent = sizer.compute(
        amount_mode="fixed",
        fixed_amount_usdt=5,
        percent=None,
        account_free_usdt=100,
        leverage=10,
        price=125,
    )

    assert intent.qty == 40
    assert intent.notional_usdt == pytest.approx(50)
    assert intent.margin_usdt == pytest.approx(5)


def test_fixed_amount_rounds_down_without_exceeding_requested_margin():
    sizer = PositionSizer(
        Contract(
            exchange="gate",
            symbol="MSTRXUSDT",
            face_value_usdt=0.01,
            min_size=1,
            size_precision=0,
        )
    )

    intent = sizer.compute(
        amount_mode="fixed",
        fixed_amount_usdt=5,
        percent=None,
        account_free_usdt=100,
        leverage=10,
        price=126.18,
    )

    assert intent.qty == 39
    assert intent.margin_usdt <= 5


def test_percent_amount_is_margin_percentage_then_leveraged():
    """余额 1000、有效比例 2%、10x = 20 USDT 保证金、200 USDT 名义仓位。"""
    sizer = PositionSizer(
        Contract(
            exchange="gate",
            symbol="ETHUSDT",
            face_value_usdt=0.001,
            min_size=1,
            size_precision=0,
        )
    )

    intent = sizer.compute(
        amount_mode="percent",
        fixed_amount_usdt=None,
        percent=2,
        account_free_usdt=1000,
        leverage=10,
        price=2500,
    )

    assert intent.qty == 80
    assert intent.notional_usdt == pytest.approx(200)
    assert intent.margin_usdt == pytest.approx(20)
