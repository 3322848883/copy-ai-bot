"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { tokenStore } from "@/lib/api";
import { WsClient, WsHandler } from "@/lib/ws";

type WsContextValue = { connected: boolean; subscribe: (channel: string, handler: WsHandler) => () => void };

const WsContext = createContext<WsContextValue>({ connected: false, subscribe: () => () => {} });

/** 全局 WS 连接：登录态建立，登出断开；订阅频道实时推送（M6 P0）。 */
export function WsProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const clientRef = useRef<WsClient | null>(null);
  const [client, setClient] = useState<WsClient | null>(null);

  useEffect(() => {
    const token = tokenStore.access;
    if (!token) {
      clientRef.current?.close();
      clientRef.current = null;
      setClient(null);
      setConnected(false);
      return;
    }
    const c = new WsClient(token);
    clientRef.current = c;
    setClient(c);
    setConnected(false);
    c.connect();
    // 连接状态轮询（简单方案：监听 open/close 事件）
    const check = window.setInterval(() => {
      const ws = (c as unknown as { ws: WebSocket | null }).ws;
      setConnected(!!ws && ws.readyState === WebSocket.OPEN);
    }, 2000);
    return () => {
      window.clearInterval(check);
      c.close();
      clientRef.current = null;
      setClient(null);
    };
  }, []);

  const subscribe = (channel: string, handler: WsHandler) => {
    if (!client) return () => {};
    return client.subscribe(channel, handler);
  };

  return <WsContext.Provider value={{ connected, subscribe }}>{children}</WsContext.Provider>;
}

export function useWsChannel(channel: string, handler: WsHandler) {
  const { subscribe } = useContext(WsContext);
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(() => {
    return subscribe(channel, (data) => handlerRef.current(data));
  }, [channel, subscribe]);
}

export function useWsConnected() {
  return useContext(WsContext).connected;
}
