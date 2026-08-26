# 跟单链路部署与核验

本版本将实时采集改为独立常驻 `poller` 服务，并加入订单幂等、真实成交字段和自动对账。

## 部署

```bash
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`api` 容器启动时会执行 `alembic upgrade head`。本版本迁移头为
`o6p7q8r9s0t1`，会为 `copy_orders` 增加真实成交数量、成交均价、交易所订单号和客户端订单号。

确认以下服务同时运行：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

关键服务包括 `api`、`worker`、`beat`、`consumer`、`poller`、`db` 和 `redis`。

## 只读诊断

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python scripts/diagnose_copy_pipeline.py
```

诊断脚本不会输出 API Key 或 Secret，也不会发送交易所订单。

## 核验重点

- `poller` 必须为 healthy；其 Redis 心跳键是 `signal:poller:heartbeat`。
- Celery beat 应包含 `order.reconcile_uncertain`，不应再周期执行 `signal.poll_live`。
- Gate API Key 必须开启永续合约读写权限、关闭提现权限，并配置服务器 IP 白名单。
- 后台订单只有在 `filled_qty > 0` 时才能显示真实成交；同时应有真实均价和交易所订单号。
- 固定金额表示每笔保证金；名义仓位约等于保证金乘杠杆。
- 比例模式先计算保证金比例，再乘杠杆换算名义仓位。

## 回滚注意

回滚应用版本前先确认旧版本是否认识新增字段。数据库迁移的 downgrade 会删除新增成交字段，
因此生产环境不应在未备份数据库的情况下执行 downgrade。
