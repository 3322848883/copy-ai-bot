"use client";

/** API 客户端：对接 FastAPI 后端（M1 T1.8）。 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as Record<string, string> || {}) };
    // 生产（同域 nginx 反代）：httpOnly cookie 自动携带；dev：Authorization header 兜底
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...options, headers, cache: "no-store", credentials: "include" });
  };

  let res = await doFetch();
  // 401 自动续期：非登录/刷新接口失败 → 尝试 refresh（cookie/body）→ 重试一次
  if (res.status === 401 && !path.startsWith("/v1/auth/")) {
    const ok = await tryRefresh();
    if (ok) res = await doFetch();
  }

  if (!res.ok) {
    let code = "unknown";
    let message = `请求失败 (${res.status})`;
    try {
      const body = await res.json();
      if (body.error) {
        code = body.error.code || code;
        message = body.error.message || message;
      }
    } catch {
      /* 非 JSON 响应 */
    }
    throw new ApiError(res.status, code, message);
  }
  return res.json() as Promise<T>;
}

/** 尝试刷新令牌（生产 httpOnly cookie 自动携带；dev 用 localStorage refresh 兜底）。 */
async function tryRefresh(): Promise<boolean> {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const body: Record<string, string> = {};
    const rt = tokenStore.refresh;
    if (rt) body.refresh_token = rt;
    const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
      method: "POST", headers, body: JSON.stringify(body), credentials: "include", cache: "no-store",
    });
    if (!res.ok) {
      tokenStore.clear();
      if (typeof window !== "undefined") window.location.href = "/login";
      return false;
    }
    const data = await res.json();
    if (data.access_token) tokenStore.set(data);
    return true;
  } catch {
    return false;
  }
}

/** Token 存取（localStorage，生产换 httpOnly cookie） */
/** 写非 HttpOnly 的 ss_access cookie：让 production `next start` 的 middleware 能识别已登录（本地无后台 httpOnly cookie 时兜底）。 */
function writeAuthCookie(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) {
    document.cookie = `ss_access=${encodeURIComponent(token)}; path=/; max-age=86400; samesite=lax`;
  } else {
    document.cookie = "ss_access=; path=/; max-age=0; samesite=lax";
  }
}

export const tokenStore = {
  get access() {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem("ss_access") || undefined;
  },
  get refresh() {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem("ss_refresh") || undefined;
  },
  set(tokens: { access_token: string; refresh_token?: string; risk_disclosure_accepted?: boolean }) {
    if (typeof window === "undefined") return;
    localStorage.setItem("ss_access", tokens.access_token);
    writeAuthCookie(tokens.access_token);
    if (tokens.refresh_token) localStorage.setItem("ss_refresh", tokens.refresh_token);
    if (tokens.risk_disclosure_accepted !== undefined) {
      localStorage.setItem("ss_risk", String(tokens.risk_disclosure_accepted));
    }
    // ★ M1 修复：通知 WsProvider 重建连接（登录/刷新令牌）
    window.dispatchEvent(new Event("ss:token-change"));
  },
  get riskAccepted(): boolean {
    if (typeof window === "undefined") return true;
    return localStorage.getItem("ss_risk") === "true";
  },
  setRiskAccepted(v: boolean) {
    if (typeof window === "undefined") return;
    localStorage.setItem("ss_risk", String(v));
  },
  clear() {
    if (typeof window === "undefined") return;
    localStorage.removeItem("ss_access");
    localStorage.removeItem("ss_refresh");
    localStorage.removeItem("ss_risk");
    writeAuthCookie(null);
    // ★ M1 修复：通知 WsProvider 断开
    window.dispatchEvent(new Event("ss:token-change"));
  },
  /** 登出：清 httpOnly cookie（后端）+ 吊销 refresh（★ H6 修复：必须带 access token）+ 跳登录页。 */
  async logout() {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const at = this.access;
      if (at) headers.Authorization = `Bearer ${at}`;
      await fetch(`${API_BASE}/v1/auth/logout`, { method: "POST", headers, credentials: "include", cache: "no-store" });
    } catch {
      /* ignore */
    }
    this.clear();
    if (typeof window !== "undefined") window.location.href = "/login";
  },
};
