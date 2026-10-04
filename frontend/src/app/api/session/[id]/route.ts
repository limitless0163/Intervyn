import { NextResponse } from "next/server";
import { serverEnv } from "@/lib/env";

// 每次请求读取服务端配置并查询最新会话，避免预渲染固化状态。
export const dynamic = "force-dynamic";

/**
 * 通过服务端代理读取会话，使 Agent 地址留在服务端并避免浏览器跨域请求。
 * 上游不可用或未返回 JSON 时，以 503 和准备中占位数据维持客户端轮询。
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const preparing = {
    session_id: id,
    status: "prep" as const,
    progress: [] as string[],
    prep_warnings: [] as string[],
    context: null,
  };

  try {
    const upstream = await fetch(
      `${serverEnv.agentApiUrl}/api/session/${encodeURIComponent(id)}`,
      {
        method: "GET",
        headers: { accept: "application/json" },
        cache: "no-store",
        // 单次查询设置超时，避免阻塞后续轮询。
        signal: AbortSignal.timeout(15_000),
      },
    );

    // 保留上游状态，未知会话的 404 不应变成准备中占位结果。
    const json = await upstream.json().catch(() => null);
    if (json === null) {
      return NextResponse.json(preparing, { status: 503 });
    }
    return NextResponse.json(json, { status: upstream.status });
  } catch {
    return NextResponse.json(preparing, { status: 503 });
  }
}
