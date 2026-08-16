import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** 前台路由守卫：未登录跳 /login（生产 httpOnly cookie 生效后启用）。 */
const PROTECTED = ["/account", "/bots", "/rewards", "/invite", "/withdraw", "/subscriptions"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  // dev：token 走 localStorage，cookie 守卫不生效（生产 nginx 同域 + httpOnly cookie 时启用）
  if (process.env.NODE_ENV === "development") return NextResponse.next();

  const hasToken = Boolean(req.cookies.get("ss_access")?.value);
  const needsAuth = PROTECTED.some((p) => pathname === p || pathname.startsWith(p + "/"));
  // ★ 修复：不再把已登录用户从 /login 弹回 "/"（cookie 与 localStorage 双源脱钩时会与页面守卫形成重定向循环）

  if (needsAuth && !hasToken) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next|api|favicon.ico|fonts|.*\\..*).*)"] };
