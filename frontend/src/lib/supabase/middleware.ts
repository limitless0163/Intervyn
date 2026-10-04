import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { gateRequest } from "@intervyn/ee";
import { isSupabaseConfigured, publicEnv } from "@/lib/env";

type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};

/**
 * 刷新认证 Cookie 后检查页面访问门控。缺少 Supabase 配置时仍以未认证身份检查，
 * 避免要求登录的发行版因配置缺失而放行；开源版门控默认允许访问。
 */
export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });
  let isAuthenticated = false;

  if (isSupabaseConfigured()) {
    const supabase = createServerClient(
      publicEnv.supabaseUrl as string,
      publicEnv.supabaseAnonKey as string,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet: CookieToSet[]) {
            cookiesToSet.forEach(({ name, value }) =>
              request.cookies.set(name, value),
            );
            supabaseResponse = NextResponse.next({ request });
            cookiesToSet.forEach(({ name, value, options }) =>
              supabaseResponse.cookies.set(name, value, options),
            );
          },
        },
      },
    );

    // 紧接客户端创建校验用户，以便本次请求与响应都使用刷新后的 Cookie。
    const { data } = await supabase.auth.getUser();
    isAuthenticated = Boolean(data.user);
  }

  // 页面可重定向到登录页；API 的鉴权由各处理器返回适当的 HTTP 状态。
  const pathname = request.nextUrl.pathname;
  if (!pathname.startsWith("/api/")) {
    const gate = gateRequest({ pathname, isAuthenticated });
    if (!gate.allow) {
      const redirectResponse = NextResponse.redirect(
        new URL(gate.redirectTo ?? "/login", request.url),
      );
      // 重定向响应也须携带刷新后的 Cookie，否则客户端会丢失更新。
      for (const cookie of supabaseResponse.cookies.getAll()) {
        redirectResponse.cookies.set(cookie);
      }
      return redirectResponse;
    }
  }

  return supabaseResponse;
}
