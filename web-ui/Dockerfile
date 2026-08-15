# M6 T6.4：前端镜像（node 20 构建 + slim 运行）
FROM node:20-alpine AS builder
WORKDIR /app
COPY web-ui/package*.json ./
RUN npm ci
COPY web-ui/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/next.config.* ./
RUN npm ci --omit=dev
EXPOSE 3000
CMD ["npm", "run", "start"]
