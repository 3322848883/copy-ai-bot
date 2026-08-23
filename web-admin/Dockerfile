# 后台镜像（独立 SPA，与前台 web-ui 完全隔离；node 20 构建 + slim 运行）
FROM node:20-alpine AS builder
WORKDIR /app
COPY web-admin/package*.json ./
RUN npm ci
COPY web-admin/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build
# ★ 生产依赖裁剪（2026-08-23）：与 web-ui 同款修复——运行阶段不再二次
#   npm ci（npm 经代理崩溃退出码 0 的隐患），prune 后直接 COPY
RUN npm prune --omit=dev

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3001
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/next.config.* ./
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3001
CMD ["npm", "run", "start"]
