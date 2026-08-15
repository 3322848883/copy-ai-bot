# M6 T6.4：后端镜像（python 3.11-slim）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    # ★ 有头采集需虚拟屏（SCRAPER_HEADLESS=false 时由 Xvfb 承载）
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

# ★ 安装 Google Chrome stable：signal_session 用 channel="chrome" 复用宿主登录态
#   （内置 chromium 版本低于 Windows Chrome 143 创建的 user_data_dir 会崩溃）
COPY chrome-stable.deb /tmp/chrome-stable.deb
RUN apt-get update && apt-get install -y --no-install-recommends /tmp/chrome-stable.deb \
    && rm -f /tmp/chrome-stable.deb \
    && rm -rf /var/lib/apt/lists/*

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
