# -*- coding: utf-8 -*-
"""数据库直连 helper（asyncpg → localhost:5433）：幂等数据准备。"""
from __future__ import annotations

import os
from typing import Any

import asyncpg

DB_DSN = os.environ.get("E2E_DB_DSN", "postgresql://signal:signal@localhost:5433/signal_saas")


def _connect() -> asyncpg.Connection:
    return asyncpg.connect(DB_DSN)


async def prep_trader(exchange: str = "gate", trader_id: str | None = None, name: str = "E2E测试带单员") -> int:
    """预插 Trader + TraderProfile（过 G04 门槛：win_rate≥55/drawdown≤30/days≥30）。幂等。"""
    conn = await _connect()
    try:
        tid = trader_id or f"e2e_trader_{int(__import__('time').time())}"
        row = await conn.fetchrow(
            "SELECT id FROM traders WHERE exchange=$1 AND trader_id=$2", exchange, tid
        )
        if row:
            return row["id"]
        trader_id_db = await conn.fetchval(
            "INSERT INTO traders(exchange, trader_id, name, followers) VALUES($1,$2,$3,0) RETURNING id",
            exchange, tid, name,
        )
        await conn.execute(
            "INSERT INTO trader_profiles(trader_id, snapshot_date, roi_7d, roi_30d, roi_90d, roi_all,"
            " win_rate_30d, win_rate_all, max_drawdown, trading_days)"
            " VALUES($1, CURRENT_DATE, 8, 12, 20, 30, 75, 80, 10, 60)",
            trader_id_db,
        )
        return trader_id_db
    finally:
        await conn.close()


async def set_order_manual(order_id: int) -> int:
    """支付订单置 manual（submit_tx failed 之后，admin 端点才可处理）。"""
    conn = await _connect()
    try:
        return await conn.execute(
            "UPDATE payment_orders SET status='manual' WHERE id=$1 AND status='failed'", order_id
        )
    finally:
        await conn.close()


async def insert_available_reward(owner_id: int, source_user_id: int, amount_usdt: float, order_id: int = 1) -> int:
    """预插可提现奖励（模拟成熟邀请奖励，避免 verifying 24/48h 等待）。"""
    conn = await _connect()
    try:
        return await conn.fetchval(
            "INSERT INTO rewards(owner_id, source_user_id, source_payment_order_id, amount_usdt, status)"
            " VALUES($1,$2,$3,$4,'available') RETURNING id",
            owner_id, source_user_id, order_id, amount_usdt,
        )
    finally:
        await conn.close()


async def get_user_id_by_email(email_addr: str) -> int | None:
    conn = await _connect()
    try:
        return await conn.fetchval("SELECT id FROM users WHERE email=$1", email_addr)
    finally:
        await conn.close()


async def prep_apikey(user_id: int, exchange: str) -> int:
    """DB 直插 ApiKey 记录（prod 模式真实交易所校验无法通过，bot 创建仅校验归属+交易所）。
    vault 加密字段用占位值；幂等：同 user+exchange 已存在则返回现有 id。"""
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT id FROM api_keys WHERE user_id=$1 AND exchange=$2", user_id, exchange
        )
        if row:
            return row["id"]
        return await conn.fetchval(
            "INSERT INTO api_keys(user_id, exchange, ciphertext, nonce, tag, aad, status)"
            " VALUES($1,$2,'e2e_cipher','e2e_nonce','e2e_tag','e2e_aad','active') RETURNING id",
            user_id, exchange,
        )
    finally:
        await conn.close()


async def count_signals() -> int:
    conn = await _connect()
    try:
        return await conn.fetchval("SELECT count(*) FROM source_signals") or 0
    finally:
        await conn.close()


async def fetch_latest_signal_row() -> dict[str, Any] | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow("SELECT * FROM source_signals ORDER BY id DESC LIMIT 1")
        return dict(row) if row else None
    finally:
        await conn.close()
