"use server";

import type { PrepRequest } from "@intervyn/shared";
import { features } from "@intervyn/ee";
import { requestPrep } from "@/services/api";
import { getUser } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/env";

export type StartSessionResult =
  | { ok: true; session_id: string }
  // error 供界面展示，reason 供客户端识别需要登录的情况。
  | {
      ok: false;
      error: string;
      reason?: "auth_required";
    };

/**
 * 返回新会话 ID，由客户端负责导航；服务端解析用户身份并绑定会话所有者。
 * 要求认证的发行版在缺少配置或用户时拒绝创建，开源版允许匿名使用。
 */
export async function startSession(
  input: PrepRequest,
): Promise<StartSessionResult> {
  let userId: string | null = null;

  if (isSupabaseConfigured()) {
    const user = await getUser();
    if (user) userId = user.id;
  }

  if (!userId && features.auth) {
    // Server Action 可被直接调用，不能只依赖页面代理的登录重定向。
    return {
      ok: false,
      error: "Sign in to start an interview.",
      reason: "auth_required",
    };
  }

  try {
    // 使用服务端认证身份覆盖输入，确保会话所有者与报告的 RLS 读取条件一致。
    const { session_id } = await requestPrep({
      ...input,
      user_id: userId ?? undefined,
    });
    return { ok: true, session_id };
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Could not reach the prep service.";
    return { ok: false, error: message };
  }
}
