# 后台镜像（独立 SPA，与前台 web-ui 完全隔离；node 20 构建 + slim 运行）
FROM node:20-alpine AS builder
WORKDIR /app
COPY web-admin/package*.json ./
RUN npm ci
COPY web-admin/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3001
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/next.config.* ./
RUN npm ci --omit=dev
EXPOSE 3001
CMD ["npm", "run", "start"]