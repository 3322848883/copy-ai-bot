# OmniAlpha 部署指南（DEPLOYMENT.md）

> 本文档覆盖四种部署形态：**服务器 + Docker**（推荐）、**服务器 + 非 Docker 原生进程**、**本地开发**（三种方式）、以及通用的环境要求 / 环境变量 / 验证 / 排障。
> 浏览器采集代理（gate.com 打通）的完整决策表见 `docs/2026-08-18-browser-proxy-deployment.md`；上线检查项见 `docs/PRODUCTION_CHECKLIST.md`；运维演练见 `docs/OPERATIONS_RUNBOOK.md`。

---

## 0. 部署形态总览（先对号入座）

| 形态 | 适用场景 | 数据库 | 需 Docker | 复杂度 |
|---|---|---|---|---|
| **服务器 + Docker（生产）** | 正式上线，域名 + TLS + 监控 | PostgreSQL 16（容器） | ✅ | 低（推荐） |
| **服务器 + 非 Docker** | 无法用 Docker 的环境 / 希望裸进程可控 | PostgreSQL + Redis 自装 | ❌ | 中高 |
| **本地 · 纯 SQLite 直跑** | 开发调试，最快上手 | SQLite（dev.db） | ❌ | 最低 |
| **本地 · Docker 辅助** | 开发但需要真实 PG/Redis/Mailhog | PostgreSQL（容器） | 部分 | 低 |
| **本地 · 全 Docker 生产栈** | 上线前在本机完整验证 prod 配置 | PostgreSQL 16（容器） | ✅ | 中 |

**核心组件（9 个运行单元）**：

| 组件 | 镜像/技术 | 端口（生产默认） | 职责 |
|---|---|---|---|
| api | python:3.11-slim + FastAPI | 8000（nginx 后） | HTTP API + WebSocket（前台 /v1 + 后台 /admin/v1） |
| worker | 同上镜像 + Celery | 无 | 信号采集主体（Playwright 浏览器）、跟单执行、支付轮询 |
| beat | 同上镜像 + Celery | 无 | 定时调度（采集/画像/清理/对账 cron） |
| consumer | 同上镜像 | 无 | 信号事件消费者（Redis pubsub → 派发跟单任务） |
| web | node:20-alpine + Next.js 15 | 3000（nginx 后） | 前台 SPA |
| web-admin | node:20-alpine + Next.js 15 | 3001（nginx 后） | 后台 SPA（独立应用） |
| db | postgres:16-alpine | 5432（仅内网） | 业务数据 |
| redis | redis:7-alpine | 6379（仅内网） | 缓存/队列/限流/登录态 |
| nginx | nginx:1.27-alpine | 80/443 | 统一入口反代 + TLS（仅生产 compose） |
| mailhog | mailhog/mailhog | 1025/8025 | 邮件捕获（**仅本地测试**，生产必须换真实 SMTP） |

---

## 1. 环境要求

### 1.1 硬件配置建议

| 项 | 最低 | 推荐 | 说明 |
|---|---|---|---|
| CPU | 2 核 | 4 核 | Playwright 采集 + Celery 并发 |
| 内存 | 4 GB | 8 GB | **关键项**：worker 内常驻 Chromium（有头 + Xvfb 虚拟屏），单实例峰值约 1-2 GB |
| 磁盘 | 40 GB | 100 GB SSD | 镜像 ~3 GB + Chromium ~1 GB + 数据库/备份增长 |
| 带宽 | 5 Mbps | 10 Mbps+ | 采集轮询 ~2 r/s + WS 推送 |

> 内存不足时 Chrome OOM 是最常见的崩溃原因。信号保留期清理任务（`signal.vacuum_retention`，每日执行）已防止数据库无限增长。

### 1.2 软件依赖

**Docker 部署（服务器/本地生产栈）**：
- Docker Engine 24+
- Docker Compose v2（`docker compose` 子命令形式）

**非 Docker 部署**：
- Python 3.11（必须 3.11，与镜像一致）
- Node.js 20（前端构建与运行）
- PostgreSQL 16
- Redis 7
- Chromium + Google Chrome（`playwright install --with-deps chromium chrome`）
- xvfb + xauth（Linux 无显示器跑有头浏览器，Akamai 拦 headless）
- nginx（反代 + TLS，生产）

### 1.3 网络要求

| 目标 | 用途 | 国内服务器 | 海外服务器 |
|---|---|---|---|
| `www.gate.com` | 信号采集（浏览器） | ❌ 需代理 | ✅ 直连 |
| Gate 官方 API | 跟单下单 / 行情 | ✅ 可直连 | ✅ |
| 四链 RPC（TRON/BSC/ETH/Aptos） | 支付确认校验 | ✅ 公共节点可达 | ✅ |
| PyPI / npm registry | 构建依赖下载 | 建议走代理或镜像 | ✅ |

> gate.com 采集被墙是国内部署唯一硬性网络要求，配置方法见 §6。

---

## 2. 服务器部署 · Docker（推荐）

### 2.1 前置准备

```bash
# 1) 获取代码
git clone https://github.com/3322848883/copy-ai-bot.git /opt/signal-saas
cd /opt/signal-saas

# 2) 实测容器内 gate.com 连通性（决定是否需要代理）
docker run --rm curlimages/curl -s -o /dev/null -w "%{http_code}\n" -m 15 https://www.gate.com
# 200 → 海外场景，无需任何代理配置；超时/非 200 → 国内场景，先做 §6
```

### 2.2 环境变量（生产 `.env`）

在项目根创建 `.env`（compose 自动读取）：

```bash
# ── 必填（缺失即启动失败，compose :? 强制 + config.py prod fail-fast 双重校验）──
APP_ENV=prod
JWT_SECRET=<openssl rand -hex 32 生成，≥32 位>
VAULT_KEY_HEX=<openssl rand -hex 32 生成，64 位 hex；用于 API Key AES-256-GCM 加密，丢失即所有绑定密钥不可解密>
POSTGRES_PASSWORD=<生产 DB 强密码>
GRAFANA_ADMIN_PASSWORD=<Grafana 管理员密码>

# ── 域名（nginx 反代 + 前端构建期注入 API base）──
SITE_DOMAIN=your-domain.com
ADMIN_SUBDOMAIN=admin.your-domain.com

# ── CORS 白名单（须精确列出前台域名 + 后台子域；禁止 * 或 localhost）──
CORS_ORIGINS=https://your-domain.com,https://admin.your-domain.com

# ── 真实 SMTP（生产拒绝 mailhog）──
SMTP_HOST=smtp.your-mail-provider.com
SMTP_PORT=587
SMTP_USER=no-reply@your-domain.com
SMTP_PASSWORD=<SMTP 授权码>
MAIL_FROM=no-reply@your-domain.com

# ── 四链 RPC（默认公共节点；生产建议自建或付费节点，主+备自动切换）──
TRON_RPC_URL=https://api.trongrid.io
BSC_RPC_URL=https://bsc-rpc.publicnode.com
ETH_RPC_URL=https://ethereum-rpc.publicnode.com

# ── 采集网络（海外服务器留空；国内按 §6 配置）──
BROWSER_PROXY_URL=
```

### 2.3 TLS 证书

nginx 挂载 `./certs` 目录（compose 已配置 `:ro` 只读）：

```bash
mkdir -p certs
# Let's Encrypt 示例（证书须同时覆盖主域 + 后台子域，用 DNS 通配符或 SAN 多域名）
certbot certonly --standalone -d your-domain.com -d admin.your-domain.com
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/
```

DNS 解析：`your-domain.com` 和 `admin.your-domain.com` 都指向服务器 IP。

### 2.4 启动

```bash
cd /opt/signal-saas

# 完整生产栈（首次构建约 10-20 分钟，含 Chromium 下载）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 后续更新（拉代码后）
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build api worker beat consumer web web-admin
```

> **国内服务器构建提速**：pip/npm/apt 下载慢时，用构建代理 override（临时文件，不入库）：
> ```bash
> # 构建 args 注入 HTTP(S)_PROXY=http://host.docker.internal:17897
> docker compose -f docker-compose.yml -f docker-compose.prod.yml \
>   -f /path/to/docker-compose.proxy-build.yml up -d --build
> ```

启动后架构（prod override 的变化）：

| 变化 | 说明 |
|---|---|
| api/web/web-admin/db/redis/mailhog **不再对外暴露端口** | 全部收敛到 nginx 80/443 统一入口 |
| 数据库连接串注入 `POSTGRES_PASSWORD` | base 里是 signal/signal 弱口令 |
| Redis 开启 AOF 持久化 | 灾备 |
| web 构建期注入 `NEXT_PUBLIC_API_BASE=https://主域` | 同源反代，避免前端请求用户本机 |
| web-admin 构建期注入 `NEXT_PUBLIC_API_BASE=https://后台子域` | 同上 |
| 新增 nginx + prometheus + grafana | TLS 终端 / 监控 |

### 2.5 生产管理员初始化

```bash
# 在容器内执行（脚本不入库，本地生效）
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python scripts/seed_prod_admin.py --email admin@your-domain.com --password <强密码>

# 首次登录后立即在后台「个人设置」启用 TOTP 双因素（推荐）
```

### 2.6 验证（部署后必做）

```bash
# 1) 容器全绿
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
# 期望：全部 Up，api/db/redis 显示 healthy

# 2) HTTPS 入口
curl -sI https://your-domain.com/healthz            # 200
curl -sI https://admin.your-domain.com/             # 200

# 3) 采集链路（约 2 分钟后看 worker 日志）
docker logs <worker容器名> --since 5m 2>&1 | grep -E "poll_live|ERR_"
# 期望：signal.poll_live ... succeeded，无 ERR_CONNECTION_CLOSED

# 4) 策略广场有数据
curl -s https://your-domain.com/v1/strategies | head

# 5) 后台登录
# 浏览器打开 https://admin.your-domain.com → 用 §2.5 的账号登录
```

### 2.7 数据持久化位置

| 路径 | 内容 | 备份策略 |
|---|---|---|
| volume `pgdata` | PostgreSQL 数据 | `scripts/backup_pg.sh` 每日 cron（保留 14 份） |
| `./data/signal_session/` | Gate 登录态浏览器 profile（模式 B 核心） | **必备份**：丢失需重新人工登录 Gate |
| `./data/scraper/`、`./data/scraper-bulk/` | 爬虫预热 cookie（防 Akamai 挑战） | 可不备份，丢失自动重建但冷启动期采集质量下降 |
| volume `promdata`/`grafanadata` | 监控数据 | 低优先级 |

---

## 3. 服务器部署 · 非 Docker（原生进程）

适用于不能用 Docker 的环境。核心思路：手动装齐依赖，用 **systemd** 管理后端 4 个进程 + 前端 2 个进程，nginx 反代。

### 3.1 系统依赖（Ubuntu/Debian 示例）

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv postgresql-16 redis-server \
                    nodejs nginx xvfb xauth curl git

# PostgreSQL 建库
sudo -u postgres psql -c "CREATE USER signal WITH PASSWORD '<强密码>';"
sudo -u postgres psql -c "CREATE DATABASE signal_saas OWNER signal;"
```

### 3.2 后端部署

```bash
cd /opt/signal-saas
git clone https://github.com/3322848883/copy-ai-bot.git .

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 安装浏览器（含系统依赖：字体/库等）
playwright install --with-deps chromium chrome

# 数据库迁移
alembic upgrade head

# .env 配置（与 §2.2 相同，另注意 DATABASE_URL/REDIS_URL 指向本机服务）
# DATABASE_URL=postgresql+asyncpg://signal:<密码>@localhost:5432/signal_saas
# REDIS_URL=redis://localhost:6379/0
# 非容器运行 BROWSER_PROXY_URL=http://127.0.0.1:7897（国内）或留空（海外）
# 采集目录改为绝对路径：
#   SIGNAL_SESSION_DATA_DIR=/opt/signal-saas/data/signal_session
#   SCRAPER_DATA_DIR=/opt/signal-saas/data/scraper
#   SCRAPER_BULK_DATA_DIR=/opt/signal-saas/data/scraper-bulk
```

### 3.3 前端构建

```bash
# 前台（构建期注入 API base）
cd web-ui
npm ci
NEXT_PUBLIC_API_BASE=https://your-domain.com npm run build

# 后台
cd ../web-admin
npm ci
NEXT_PUBLIC_API_BASE=https://admin.your-domain.com npm run build
```

### 3.4 systemd 服务单元

后端 4 个进程（api / worker / beat / consumer）。**worker 需要 Xvfb 虚拟屏**（容器里由 docker-entrypoint.sh 自动处理，裸机需自己做）：

```ini
# /etc/systemd/system/signal-xvfb.service —— 虚拟屏（worker 有头采集依赖）
[Unit]
Description=Xvfb virtual display for headful scraping
[Service]
ExecStart=/usr/bin/Xvfb :99 -screen 0 1440x900x24 -nolisten tcp -nolisten unix
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-api.service
[Unit]
Description=OmniAlpha API (FastAPI)
After=network.target postgresql.service redis-server.service
[Service]
WorkingDirectory=/opt/signal-saas
EnvironmentFile=/opt/signal-saas/.env
ExecStart=/opt/signal-saas/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-worker.service
[Unit]
Description=OmniAlpha Celery worker (signal scraping + copy execution)
After=network.target postgresql.service redis-server.service signal-xvfb.service
[Service]
WorkingDirectory=/opt/signal-saas
EnvironmentFile=/opt/signal-saas/.env
Environment=DISPLAY=:99
ExecStartPre=/bin/bash -c 'for d in /opt/signal-saas/data/signal_session /opt/signal-saas/data/scraper /opt/signal-saas/data/scraper-bulk; do [ -d "$d" ] && rm -f "$d"/Singleton* "$d"/.com.google.Chrome.*; done; true'
ExecStart=/opt/signal-saas/.venv/bin/celery -A api.workers.celery_app:celery_app worker --loglevel=info
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-beat.service
[Unit]
Description=OmniAlpha Celery beat (scheduler)
After=network.target redis-server.service
[Service]
WorkingDirectory=/opt/signal-saas
EnvironmentFile=/opt/signal-saas/.env
ExecStart=/opt/signal-saas/.venv/bin/celery -A api.workers.celery_app:celery_app beat --loglevel=info
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-consumer.service
[Unit]
Description=OmniAlpha signal event consumer
After=network.target redis-server.service
[Service]
WorkingDirectory=/opt/signal-saas
EnvironmentFile=/opt/signal-saas/.env
ExecStart=/opt/signal-saas/.venv/bin/python -m api.workers.consumer_signal
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-web.service —— 前台 Next.js
[Unit]
Description=OmniAlpha web-ui (Next.js)
After=network.target
[Service]
WorkingDirectory=/opt/signal-saas/web-ui
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-web-admin.service —— 后台 Next.js
[Unit]
Description=OmniAlpha web-admin (Next.js)
After=network.target
[Service]
WorkingDirectory=/opt/signal-saas/web-admin
Environment=NODE_ENV=production
Environment=PORT=3001
ExecStart=/usr/bin/npm run start
Restart=always
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now signal-xvfb signal-api signal-worker signal-beat signal-consumer signal-web signal-web-admin
```

> `ExecStartPre` 的 SingletonLock 清理对应容器版 docker-entrypoint.sh 的行为：进程异常退出后 Chrome profile 会残留指向死进程的锁文件，下次启动弹「profile in use」永久阻塞采集。

### 3.5 nginx 反代（非 Docker 版）

容器版用 envsubst 注入域名，这里直接写死。与 `deploy/nginx/nginx.conf` 结构一致：

```nginx
# /etc/nginx/sites-available/signal-saas.conf
worker_processes auto;
events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    sendfile on;
    client_max_body_size 2m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;

    upstream api_upstream { server 127.0.0.1:8000; }
    upstream web_upstream { server 127.0.0.1:3000; }
    upstream admin_upstream { server 127.0.0.1:3001; }

    server {
        listen 80 default_server;
        server_name _;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        http2 on;
        server_name your-domain.com;
        ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

        location /v1/ { proxy_pass http://api_upstream; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-Proto $scheme; }
        location /admin/v1/ { proxy_pass http://api_upstream; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-Proto $scheme; }
        location /ws/ {
            proxy_pass http://api_upstream;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 300s;
        }
        location /healthz { proxy_pass http://api_upstream; proxy_set_header Host $host; }
        location / { proxy_pass http://web_upstream; proxy_set_header Host $host; }
    }

    server {
        listen 443 ssl;
        http2 on;
        server_name admin.your-domain.com;
        ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

        location /admin/v1/ { proxy_pass http://api_upstream; proxy_set_header Host $host; }
        location /v1/ { proxy_pass http://api_upstream; proxy_set_header Host $host; }
        location / { proxy_pass http://admin_upstream; proxy_set_header Host $host; }
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/signal-saas.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

> 生产建议：`/metrics` 和 `/docs` 不要暴露到公网（预上线检查项），或加 IP 白名单。

### 3.6 非 Docker 与 Docker 的行为差异

| 项 | Docker | 非 Docker | 注意 |
|---|---|---|---|
| SingletonLock 清理 | entrypoint 自动 | systemd ExecStartPre 手动 | 忘配会采集卡死 |
| Xvfb 虚拟屏 | entrypoint 自动 | 独立 systemd 单元 | worker 必须依赖它 |
| 孤儿 Chrome 回收 | `init: true`（容器 PID1 回收） | systemd 自动 | 无需额外处理 |
| 数据库迁移 | api 启动命令自动 `alembic upgrade head` | 手动执行 | 升级时记得先跑 |
| 时区 | 容器默认 UTC（beat cron 已按 UTC 设计） | 服务器本地时区 | beat 调度相位可能偏移，建议服务器也用 UTC |

---

## 4. 本地开发部署

三种方式按需选择。

### 4.1 方式 A：纯 SQLite 直跑（最快上手，零 Docker）

```bash
# 1) venv + 依赖
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install --with-deps chromium chrome

# 2) 环境变量（SQLite + 本机 Redis）
export DATABASE_URL=sqlite+aiosqlite:///./dev.db
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET=dev-secret-please-change-in-prod
export APP_ENV=dev

# 3) 启动后端
alembic upgrade head
python scripts/rebuild_devdb.py    # 重建演示数据
python scripts/seed_demo.py
uvicorn api.main:app --reload
# 健康检查: http://localhost:8000/healthz
# API 文档: http://localhost:8000/docs

# 4) 前端（两个终端）
cd web-ui && npm install && npm run dev      # 前台 http://localhost:3000
cd web-admin && npm install && npm run dev   # 后台 http://localhost:3001
```

> 需要 Redis 在本机跑着（`redis-server`），SQLite 模式不支持部分 PG 特性（部分索引等），完整功能验证建议用方式 C。

### 4.2 方式 B：Docker 辅助（只有基础设施容器化，进程跑本机）

```bash
# 起 db + redis + mailhog（docker-compose.local.yml）
docker compose -f docker-compose.local.yml up -d

# .env 用仓库自带默认值（PG 5432 / Redis 6380 / Mailhog 1025）
source .venv/bin/activate
alembic upgrade head
uvicorn api.main:app --reload
# 另开终端
celery -A api.workers.celery_app:celery_app worker --loglevel=info
celery -A api.workers.celery_app:celery_app beat --loglevel=info
python -m api.workers.consumer_signal
```

邮件验证码在 Mailhog Web UI 查看：http://localhost:8025

### 4.3 方式 C：全 Docker 生产栈（本地生产测试，验证 prod 配置）

在无域名/无 TLS 的本机验证 `APP_ENV=prod` 完整栈（含 fail-fast 校验）：

```bash
cd C:\sa-src   # Windows 必须 ASCII 路径，见 §4.4

# 代理中继（国内网络必须先启动；海外可跳过）
python scripts/proxy_relay.py     # 监听 0.0.0.0:17897 → 127.0.0.1:7897（需本机代理在 7897）

# 完整栈（.env.prod-local 提供本地测试密钥）
docker compose --env-file .env.prod-local \
  -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.prod.local.yml \
  -p signal-saas-prod up -d --build
```

本地生产栈端口映射（避开 WSL 常用端口）：

| 服务 | 端口 |
|---|---|
| api | **8001** |
| web（前台） | **3002** |
| web-admin（后台） | **3001** |
| db | 5433 |
| redis | 6381 |
| mailhog UI / SMTP | 8026 / 1026 |

验证：
```bash
curl -s http://localhost:8001/healthz
# 浏览器: http://localhost:3002（前台）、http://localhost:3001（后台）
# Mailhog: http://localhost:8026
```

### 4.4 Windows 专属注意事项（实测坑）

| 坑 | 规则 |
|---|---|
| **中文路径触发 Docker bake gRPC 错误** | compose 命令必须在 ASCII 路径执行（如 `C:\sa-src`），仓库不能放在含中文的目录 |
| **Docker Desktop 重启后容器异常** | 重启 Docker Desktop 前先 `wsl --shutdown`；若引擎崩溃：结束全部 docker 进程（含 com.docker.backend 残留）→ 重启 Docker Desktop → db/redis 容器可能不自启，手动 `docker start` |
| **代理中继不随开机自启** | `scripts/proxy_relay.py` 手动进程，重启电脑后需重新拉起（或配任务计划程序登录时触发） |
| **构建超时/龟速** | 用构建代理 override：`C:\Temp\docker-compose.proxy-build.yml`（需先跑 `C:\Temp\proxy_relay.py`） |
| **PowerShell 5.1 `Get-Date -UFormat %s` 有 bug** | 跨时钟验证用 `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` |

---

## 5. 浏览器采集网络（gate.com 打通）

完整决策表与步骤见 `docs/2026-08-18-browser-proxy-deployment.md`，速查：

| 场景 | BROWSER_PROXY_URL | 需中继 relay |
|---|---|---|
| 海外服务器 + Docker | 留空 | ❌ |
| 国内服务器 + Docker（代理仅监听 127.0.0.1） | `http://host.docker.internal:17897` | ✅ |
| 国内服务器 + Docker（代理监听 0.0.0.0） | `http://host.docker.internal:7897` | ❌ |
| 任意机器 + 非 Docker | `http://127.0.0.1:7897` | ❌ 永远不需要 |

```bash
# 先测再配
docker exec <api容器> curl -s -o /dev/null -w "%{http_code}\n" -m 15 https://www.gate.com

# 国内 Docker 场景三件套：
# 1) Linux 加 host-gateway（prod.local.yml 已带）
#    extra_hosts: ["host.docker.internal:host-gateway"]
# 2) 中继 systemd 常驻（signal-relay.service，Restart=always）
# 3) 防火墙限制 17897 仅 Docker 网段（172.17.0.0/16）——⚠️ 否则=公网开放代理
```

---

## 6. 环境变量完整参考

### 6.1 生产必填（缺失即启动失败）

| 变量 | 说明 |
|---|---|
| `APP_ENV` | `prod`（触发 fail-fast 全量校验） |
| `JWT_SECRET` | ≥32 位随机串（拒绝默认值） |
| `VAULT_KEY_HEX` | 64 位 hex（API Key AES-256-GCM 主密钥，**丢失不可恢复**） |
| `DATABASE_URL` | 生产 PG 连接串（拒绝本地默认串） |
| `POSTGRES_PASSWORD` | compose 强制注入 |
| `SITE_DOMAIN` / `ADMIN_SUBDOMAIN` | 前台主域 / 后台子域（TLS + 前端构建注入） |
| `CORS_ORIGINS` | 精确域名白名单（含前台域名 + 后台子域；禁止 `*`/localhost） |
| `SMTP_HOST/PORT/USER/PASSWORD/MAIL_FROM` | 真实 SMTP（拒绝 mailhog） |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 管理员密码 |

### 6.2 可选（有默认值）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ENABLED_EXCHANGES` | `gate` | V1 上线白名单，仅 gate |
| `TRON/BSC/ETH_RPC_URL` | 公共节点 | 四链支付确认（建议生产换自建/付费） |
| `BROWSER_PROXY_URL` | 空 | 浏览器采集代理（§5） |
| `SCRAPER_REAL` | `1` | 真实采集开关（0=mock） |
| `SCRAPER_HEADLESS` | `false` | **必须 false**：Gate Akamai 拦 headless |
| `SIGNAL_SESSION_ENABLED` | `true` | 模式 B 持久化登录会话 |
| `SIGNAL_SESSION_DATA_DIR` | `/app/data/signal_session` | 登录态落盘目录 |
| `SCRAPER_DATA_DIR` / `SCRAPER_BULK_DATA_DIR` | `/app/data/scraper` / `...-bulk` | 爬虫 profile 持久化 |
| `SIGNAL_RETENTION_DAYS` | `90` | 源信号保留期（每日清理任务） |
| `POSITION_SNAPSHOT_RETENTION_DAYS` | `30` | 已关闭持仓快照保留期 |
| `CORS_ALLOW_LOCAL_TEST` | 空 | 仅本地 prod 测试放行 localhost |

### 6.3 本地开发默认（`.env`）

见仓库根 `.env`（APP_ENV=dev / SQLite 可覆盖 / Mailhog 1025 / 宽松 CORS）。

---

## 7. 部署后验证清单

```bash
# 基础
[ ] 容器/服务全部 Up（healthy）
[ ] /healthz 返回 200（HTTP + 经 nginx 的 HTTPS 两路）
[ ] /v1/config 公开端点返回参数（邀请比例/确认数/提现门槛等）

# 前端
[ ] 前台首页打开，行情卡片正常（Gate 公开 ticker 失败时隐藏，不算失败项）
[ ] 注册 → 收到验证码邮件 → 激活 → 登录（生产真实 SMTP；本地看 Mailhog）
[ ] 后台子域打开，管理员登录成功

# 采集
[ ] worker 日志：signal.poll_live succeeded、无 ERR_CONNECTION_CLOSED
[ ] 后台「信号源审核」→ 搜索带单员返回结果
[ ] 策略广场出现上架策略（首次需后台搜索→设为数据源→上架）

# 资金流（真实小额测试后清理）
[ ] 四链收款地址已配置（后台「订单管理→平台收款地址」）
[ ] 小额 USDT 支付 → 自动核实 → 套餐开通
[ ] 提现申请 → 后台审批 → 链上打款 → 状态闭环

# 安全
[ ] 管理员启用 TOTP（后台个人设置）
[ ] 测试数据清理（零残留）
[ ] Grafana 告警通知渠道已绑定（Alerting → Contact points）
```

---

## 8. 常见问题排查

| 现象 | 原因 | 处理 |
|---|---|---|
| api 容器启动即退出 | prod fail-fast：密钥/SMTP/CORS 缺失或弱值 | `docker logs <api>` 看具体报错，补齐 §6.1 |
| 采集每轮 `ERR_CONNECTION_CLOSED` | 未配代理（国内） | §5 配 BROWSER_PROXY_URL + 中继 |
| `ERR_PROXY_CONNECTION_FAILED` | 中继或上游代理挂了 | `systemctl status signal-relay` / Clash 进程；防火墙拦截 |
| `ERR_TIMED_OUT` + gate.com 403 | 代理出口 IP 被 Akamai 风控 | Clash 换节点；确认 SCRAPER_HEADLESS=false |
| 搜索带单员无反应 | Chrome profile SingletonLock 残留（跨容器共享） | 已修复（entrypoint + start_login 双路清理）；仍复发则手动删 `data/*/Singleton*` |
| worker 内存持续增长 | 浏览器任务未正常退出（罕见） | `docker restart <worker>`；检查日志是否 poll_live 卡死 |
| 磁盘增长 | source_signals/position_snapshots 积累 | `signal.vacuum_retention` 每日自动清理（§6.2 保留期可调） |
| 前端请求打到 127.0.0.1:8000 | 构建期 NEXT_PUBLIC_API_BASE 未注入域名 | 用 prod compose 重建 web/web-admin（不要用 base compose 上生产） |
| Windows compose 报 gRPC 错误 | 仓库路径含中文 | 移到 ASCII 路径（C:\sa-src） |
| 容器重建后采集质量骤降 | 爬虫预热 cookie 丢失 | 已挂载 volume 持久化；确认 `./data/scraper` 挂载存在 |
| 登录态丢失（模式 B 失效） | signal_session 目录未持久化 | 确认 volume 挂载；丢失需后台重新「登录 Gate」 |
| WS 连不上 | nginx 未配 Upgrade 头 | 检查 `/ws/` location 的 proxy_set_header Upgrade/Connection |

---

## 9. 相关文档

- `README.md` — 项目总览与快速开始
- `docs/PRODUCTION_CHECKLIST.md` — 上线检查清单（逐项打勾）
- `docs/OPERATIONS_RUNBOOK.md` — 运维演练（备份/密钥轮换/压测/灰度/回滚/TOTP）
- `docs/2026-08-18-browser-proxy-deployment.md` — 采集代理与中继完整方案
- `docs/2026-08-19-production-hardening.md` — 上线全局核查修复明细
