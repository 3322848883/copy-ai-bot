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
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as Record<string, string> || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, cache: "no-store" });

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

/** Token 存取（localStorage，生产换 httpOnly cookie） */
export const tokenStore = {
  get access() {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem("ss_access") || undefined;
  },
  // M5 T5.1：后台独立 token（aud=admin）
  get adminAccess() {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem("ss_admin_access") || undefined;
  },
  setAdmin(token: string) {
    if (typeof window === "undefined") return;
    localStorage.setItem("ss_admin_access", token);
  },
  clearAdmin() {
    if (typeof window === "undefined") return;
    localStorage.removeItem("ss_admin_access");
  },
  get refresh() {
    if (typeof window === "undefined") return undefined;
    return localStorage.getItem("ss_refresh") || undefined;
  },
  set(tokens: { access_token: string; refresh_token?: string; risk_disclosure_accepted?: boolean }) {
    if (typeof window === "undefined") return;
    localStorage.setItem("ss_access", tokens.access_token);
    if (tokens.refresh_token) localStorage.setItem("ss_refresh", tokens.refresh_token);
    if (tokens.risk_disclosure_accepted !== undefined) {
      localStorage.setItem("ss_risk", String(tokens.risk_disclosure_accepted));
    }
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
  },
};
