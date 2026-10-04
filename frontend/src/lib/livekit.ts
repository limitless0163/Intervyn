import "server-only";
import {
  AccessToken,
  RoomAgentDispatch,
  RoomConfiguration,
} from "livekit-server-sdk";
import { isLiveKitConfigured, serverEnv } from "@/lib/env";

export interface CreateInterviewTokenArgs {
  /** 房间名使用已验证的面试 session_id，调度元数据也复用此值。 */
  room: string;
  identity: string;
  name?: string;
  metadata?: Record<string, unknown>;
}

export interface InterviewToken {
  token: string;
  url: string;
}

/**
 * 签发房间加入令牌并显式调度面试官；缺少 LiveKit 配置时抛出异常。
 * 调度元数据携带 session_id，使工作进程无需依赖房间元数据即可加载上下文。
 */
export async function createInterviewToken({
  room,
  identity,
  name,
  metadata,
}: CreateInterviewTokenArgs): Promise<InterviewToken> {
  if (!isLiveKitConfigured()) {
    throw new Error(
      "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET.",
    );
  }

  const at = new AccessToken(
    serverEnv.livekitApiKey,
    serverEnv.livekitApiSecret,
    {
      identity,
      name,
      metadata: metadata ? JSON.stringify(metadata) : undefined,
    },
  );

  at.addGrant({
    room,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  // 仅加入房间不会启动面试官，调度名称须与工作进程注册名称一致。
  at.roomConfig = new RoomConfiguration({
    agents: [
      new RoomAgentDispatch({
        agentName: serverEnv.livekitAgentName,
        metadata: JSON.stringify({ session_id: room }),
      }),
    ],
  });

  const token = await at.toJwt();
  return { token, url: serverEnv.livekitUrl as string };
}
