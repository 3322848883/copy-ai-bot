# 浏览器采集代理（BROWSER_PROXY_URL）与中继部署说明

> 适用范围：Playwright 采集 gate.com 等被墙站点的网络打通方案。
> 覆盖三种落地形态：**海外服务器（免代理）**、**国内服务器 + Docker（中继）**、**任意机器非 Docker 原生运行（免中继）**。
> 关联改动：`api/core/config.py`（`browser_proxy_url` 配置项）、`docker-compose.prod.local.yml`、`scripts/proxy_relay.py`。

## 1. 背景与原理

- 采集链路：worker/api 进程内 Playwright 拉起 Chromium 访问 `www.gate.com`。国内网络直连会被重置，表现为 `net::ERR_CONNECTION_CLOSED`（采集功能整体瘫痪，每分钟刷错误日志）。
- **Chromium 不读 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量**，必须在 `launch(proxy={"server": ...})` 显式传入。为此新增配置项：

| 配置项 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `browser_proxy_url` | `BROWSER_PROXY_URL` | 空（不走代理） | 浏览器采集统一代理出口；空 = 直连 |

传参位置（共 6 处，全部已改）：`api/services/scraper/adapters/gate.py`（4 处 launch）、`api/services/signal_session/service.py`（2 处 launch）。

- **为什么需要"中继"（relay）**：Clash/Mihomo 出于安全默认只监听 `127.0.0.1:7897`，而 Docker 容器内的 `127.0.0.1` 是容器自身回环，**访问不到宿主的回环代理**。`scripts/proxy_relay.py` 把宿主 `0.0.0.0:17897` 的流量转发到 `127.0.0.1:7897`，使容器经 `host.docker.internal:17897` 走上宿主代理——无需改动 Clash 配置。

## 2. 场景决策表（先对号入座，再动手）

| 场景 | gate.com 直连 | 需 BROWSER_PROXY_URL | 需中继 | 取值 |
|---|---|---|---|---|
| A. 海外服务器 + Docker | ✅ 可达 | ❌ | ❌ | 留空（默认） |
| B. 国内服务器 + Docker，代理仅监听 127.0.0.1 | ❌ | ✅ | ✅ | `http://host.docker.internal:17897` |
| C. 国内服务器 + Docker，代理已监听 0.0.0.0/局域网 | ❌ | ✅ | ❌ | `http://host.docker.internal:7897`（或宿主内网 IP） |
| D. 任意机器 + **非 Docker** 原生运行 | 视网络 | 视网络 | ❌ **永远不需要** | `http://127.0.0.1:7897` |
| E. 海外服务器 + 非 Docker | ✅ | ❌ | ❌ | 留空 |

**先测再配**——容器内验证 gate.com 是否直连可达：

```bash
docker exec signal-saas-prod-api-1 curl -s -o /dev/null -w "%{http_code}\n" -m 15 https://www.gate.com
# 200 → 场景 A/E，什么都不用配；超时/非 200 → 走 B/C/D
```

## 3. 服务器部署 · Docker（场景 B 完整步骤）

### 3.1 Linux 必做：`host.docker.internal` 映射

Linux Docker **默认不解析** `host.docker.internal`（Docker Desktop 才自带）。`docker-compose.prod.local.yml` 的 api/worker 已加：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"   # Docker Desktop 上无副作用，Linux 上必需
```

也可绕开：直接用网桥 IP `http://172.17.0.1:17897` 或宿主内网 IP。

### 3.2 中继常驻（systemd 自启 + 崩溃自拉起）

`scripts/proxy_relay.py` 仅用标准库（Python ≥ 3.8，无三方依赖）。创建 `/etc/systemd/system/signal-relay.service`：

```ini
[Unit]
Description=signal-saas proxy relay (0.0.0.0:17897 -> 127.0.0.1:7897)
After=network.target

[Service]
Type=simple
# 部署目录按实际调整；WorkingDirectory 决定 .env 之外的相对路径
WorkingDirectory=/opt/signal-saas
ExecStart=/usr/bin/python3 scripts/proxy_relay.py
Restart=always
RestartSec=3
# 环境变量可覆盖默认端口（一般不用动）：
# Environment=RELAY_LISTEN_PORT=17897
# Environment=RELAY_UPSTREAM_HOST=127.0.0.1
# Environment=RELAY_UPSTREAM_PORT=7897
# 加固：仅允许 docker 组外的普通用户运行则取消注释
# User=signalsvc

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now signal-relay
systemctl status signal-relay        # 应显示 active (running)
```

临时方式（不做 systemd 时的兜底）：

```bash
nohup python3 scripts/proxy_relay.py >/var/log/signal-relay.log 2>&1 &
```

### 3.3 防火墙（⚠️ 安全必做）

中继监听 `0.0.0.0` **等于在服务器上开了一个无认证代理端口**，必须限制来源为 Docker 网段，否则会沦为公网开放代理：

```bash
# ufw（Ubuntu 默认）
sudo ufw allow from 172.17.0.0/16 to any port 17897 proto tcp
sudo ufw deny 17897/tcp

# 或 iptables（默认 docker0 网桥 172.17.0.0/16；自定义 compose 网段自行替换）
sudo iptables -I INPUT -p tcp --dport 17897 -s 172.17.0.0/16 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 17897 -j DROP
```

### 3.4 compose 配置与启动顺序

`docker-compose.prod.local.yml` 已配（api + worker 都要，采集主要在 worker）：

```yaml
environment:
  BROWSER_PROXY_URL: http://host.docker.internal:17897
```

**启动顺序**：代理（Clash/Mihomo）→ 中继（signal-relay）→ `docker compose up -d`。
中继不在时栈也能启动，但采集任务每轮失败重试（错误日志 `ERR_PROXY_CONNECTION_FAILED`）。

### 3.5 验证（三层）

```bash
# 1) 容器 → 中继 → 代理 出网
docker exec signal-saas-prod-api-1 curl -s -o /dev/null -w "%{http_code}\n" \
  -x http://host.docker.internal:17897 -m 15 https://www.gstatic.com/generate_204
# 期望 204

# 2) 容器 → gate.com
docker exec signal-saas-prod-api-1 curl -s -o /dev/null -w "%{http_code}\n" \
  -x http://host.docker.internal:17897 -m 15 https://www.gate.com
# 期望 200

# 3) worker 日志：launch 行应带 proxy=，且不再出现 ERR_CONNECTION_CLOSED
docker logs signal-saas-prod-worker-1 --since 5m 2>&1 | grep -E "proxy=|ERR_"
# 期望：launch persistent chrome (headless=... proxy=http://host.docker.internal:17897)
#       且 signal.poll_live ... succeeded
```

## 4. 服务器部署 · 非 Docker 原生运行（场景 D）

**原生进程直接跑在宿主上，`127.0.0.1:7897` 天然可达——永远不需要中继。** 中继仅是"容器 → 宿主回环"的桥，与本机代理同进程组时没有存在意义。

### 4.1 配置

项目根 `.env`（config.py 以绝对路径加载 `PROJECT_ROOT/.env`，与进程启动目录无关）：

```bash
# 有代理（国内网络）：
BROWSER_PROXY_URL=http://127.0.0.1:7897
# 无代理（海外服务器/已直连）：删除该行或留空
```

### 4.2 启动顺序与命令

```bash
# 1) 代理（如需）
# 2) API（采集逻辑也可能在 api 进程触发）
source .venv/bin/activate
alembic upgrade head
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3) 采集主体：celery worker + beat
celery -A api.workers.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4
celery -A api.workers.celery_app:celery_app beat --loglevel=info
```

### 4.3 验证

```bash
curl -s -o /dev/null -w "%{http_code}\n" -x http://127.0.0.1:7897 -m 15 https://www.gate.com   # 期望 200
# worker 日志出现 launch ... proxy=http://127.0.0.1:7897 即生效
```

## 5. Windows 开发机（当前本机现状，备忘）

```powershell
# 中继（已正式化到项目内；重启电脑后需重新拉起）
Start-Process python -ArgumentList "scripts\proxy_relay.py" -WindowStyle Hidden -WorkingDirectory C:\sa-src
# 验证
curl.exe -s -o NUL -w "%{http_code}`n" -x http://127.0.0.1:17897 -I https://www.gstatic.com/generate_204   # 204
```

- 开机自启（可选）：任务计划程序 → 触发器"登录时" → 操作 `python C:\sa-src\scripts\proxy_relay.py`。
- `docker-compose.prod.local.yml` 已配 `BROWSER_PROXY_URL=http://host.docker.internal:17897`。
- 顺序：中继 → `docker compose up`。

## 6. 构建期代理（另一条线，勿与运行期混淆）

| 线路 | 用途 | 机制 |
|---|---|---|
| **运行期**（本文档） | 浏览器采集出网 | `BROWSER_PROXY_URL` → launch(proxy=) |
| **构建期** | pip/npm/apt 下载提速 | compose override 传 build args `HTTP(S)_PROXY=http://host.docker.internal:17897` |
| **镜像拉取** | 拉基础镜像 | `docker pull docker.1ms.run/library/<img>` 再 `docker tag` |

三条线互相独立；构建期 override 文件见开发机 `C:\Temp\docker-compose.proxy-build.yml`（临时，不入库也可用）。

## 7. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `net::ERR_CONNECTION_CLOSED` 刷屏 | 未配代理或未生效 | 检查 `docker exec <容器> env \| grep BROWSER` 是否传入；worker/api 都要配 |
| launch 日志 `proxy=off` | 环境变量没进容器 | compose 该服务漏配 `BROWSER_PROXY_URL` |
| `ERR_PROXY_CONNECTION_FAILED` / `ERR_TIMED_OUT` | 中继或上游代理挂了 | `systemctl status signal-relay`、Clash 进程/端口；防火墙是否误拦 |
| Linux 容器解析不了 host.docker.internal | 未加 host-gateway | `extra_hosts: ["host.docker.internal:host-gateway"]` 或改用 `172.17.0.1` |
| 中继通但 gate.com 403（Akamai） | 代理出口 IP 被风控 | Clash 切换出口节点；或按既有方案走有头 + xvfb |
| 公网扫到 17897 开放代理 | 防火墙未限制 | §3.3 立即加 Docker 网段白名单 + DROP |

## 8. 已知残留（上线前人工项）

- Mode2 `INVALID_KEY / invalid user`：非网络故障，需后台管理完成 Gate 登录（signal_session 持久化登录态）后才可用。
- `JWT_SECRET`/`VAULT_KEY_HEX` 仍是本地测试弱默认值，公网上线前必须替换（见 PRODUCTION_CHECKLIST §1、§4）。
