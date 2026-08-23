# M6 T6.4：前端镜像（node 20 构建 + slim 运行）
FROM node:20-alpine AS builder
WORKDIR /app
COPY web-ui/package*.json ./
RUN npm ci
COPY web-ui/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build
# ★ 生产依赖裁剪（2026-08-23）：构建后原地 prune，运行阶段直接 COPY——
#   消除运行期第二次 npm ci（曾因代理抖动触发 npm "Exit handler never
#   called" 崩溃且退出码为 0，产出无 next 的残缺镜像层并被缓存复用）
RUN npm prune --omit=dev

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/next.config.* ./
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "start"]
