"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { tokenStore } from "@/lib/api";
import { WsClient, WsHandler } from "@/lib/ws";

type WsContextValue = { connected: boolean; subscribe: (channel: string, handler: WsHandler) => () => void };

const WsContext = createContext<WsContextValue>({ connected: false, subscribe: () => () => {} });

/** 全局 WS 连接：登录态建立，登出断开；订阅频道实时推送（M6 P0）。
 *  ★ M1 修复：监听 ss:token-change 事件（tokenStore.set/clear 触发），
 *    登录/登出软导航后自动重建连接，无需整页刷新。
 */
export function WsProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const clientRef = useRef<WsClient | null>(null);
  const [client, setClient] = useState<WsClient | null>(null);
  const [token, setToken] = useState<string | undefined>(undefined);

  // token 同步：挂载 + 事件驱动（登录/登出/刷新令牌）
  useEffect(() => {
    const sync = () => setToken(tokenStore.access);
    sync();
    window.addEventListener("ss:token-change", sync);
    return () => window.removeEventListener("ss:token-change", sync);
  }, []);

  useEffect(() => {
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
  }, [token]);

  const subscribe = useCallback(
    (channel: string, handler: WsHandler) => {
      if (!client) return () => {};
      return client.subscribe(channel, handler);
    },
    [client],
  );

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
