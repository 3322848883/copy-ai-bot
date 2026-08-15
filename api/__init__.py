# signal-saas API 包
"""FastAPI 单体后端（决策 B：官方直连，无 ccxt）。

19 个业务模块 + 2 个前端应用 = 21 个核心模块。
模块间通过函数调用 + 依赖注入协作，跨模块事件用 Redis Pub/Sub 与 Celery 队列。
"""
