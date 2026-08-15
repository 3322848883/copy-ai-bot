"use client";

/** WebSocket 客户端：连接 / 心跳 / 重连 / 频道分发（M6 P0）。 */
const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE || "ws://127.0.0.1:8000";

export type WsHandler = (data: unknown) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<WsHandler>>();
  private token: string;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private closed = false;
  private reconnectDelay = 2000;

  constructor(token: string) {
    this.token = token;
  }

  connect() {
    if (this.closed || this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/stream?token=${encodeURIComponent(this.token)}`);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      this.reconnectDelay = 2000;
      this.startHeartbeat();
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string);
        if (msg && msg.channel) this.dispatch(msg.channel, msg.data);
      } catch {
        /* 忽略非 JSON */
      }
    };
    this.ws.onclose = () => {
      this.stopHeartbeat();
      if (!this.closed) this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      try {
        this.ws?.close();
      } catch {
        /* noop */
      }
    };
  }

  subscribe(channel: string, handler: WsHandler): () => void {
    if (!this.handlers.has(channel)) this.handlers.set(channel, new Set());
    this.handlers.get(channel)!.add(handler);
    return () => {
      this.handlers.get(channel)?.delete(handler);
    };
  }

  close() {
    this.closed = true;
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.stopHeartbeat();
    try {
      this.ws?.close();
    } catch {
      /* noop */
    }
    this.ws = null;
  }

  private dispatch(channel: string, data: unknown) {
    this.handlers.get(channel)?.forEach((h) => {
      try {
        h(data);
      } catch {
        /* handler 异常不影响其他 */
      }
    });
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30_000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) window.clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private scheduleReconnect() {
    if (this.reconnectTimer || this.closed) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 15_000);
  }
}
