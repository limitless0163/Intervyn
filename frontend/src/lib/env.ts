/**
 * 延迟读取配置，允许缺少密钥时构建。NEXT_PUBLIC_* 必须静态引用，
 * 才能由 Next.js 在构建时内联；动态索引无法在浏览器中读取。
 */

/** 浏览器可用的配置，取值在构建时内联。 */
export const publicEnv = {
  get supabaseUrl(): string | undefined {
    return process.env.NEXT_PUBLIC_SUPABASE_URL || undefined;
  },
  get supabaseAnonKey(): string | undefined {
    return process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || undefined;
  },
  get appUrl(): string {
    return process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  },
};

/** 仅供服务端使用；客户端组件不得导入此配置对象。 */
export const serverEnv = {
  get supabaseServiceRoleKey(): string | undefined {
    return process.env.SUPABASE_SERVICE_ROLE_KEY || undefined;
  },
  get livekitUrl(): string | undefined {
    return process.env.LIVEKIT_URL || undefined;
  },
  get livekitApiKey(): string | undefined {
    return process.env.LIVEKIT_API_KEY || undefined;
  },
  get livekitApiSecret(): string | undefined {
    return process.env.LIVEKIT_API_SECRET || undefined;
  },
  /** 必须与工作进程的 LIVEKIT_AGENT_NAME 一致，否则显式调度找不到面试官。 */
  get livekitAgentName(): string {
    return process.env.LIVEKIT_AGENT_NAME || "intervyn-interviewer";
  },
  get r2AccountId(): string | undefined {
    return process.env.R2_ACCOUNT_ID || undefined;
  },
  get r2AccessKeyId(): string | undefined {
    return process.env.R2_ACCESS_KEY_ID || undefined;
  },
  get r2SecretAccessKey(): string | undefined {
    return process.env.R2_SECRET_ACCESS_KEY || undefined;
  },
  get r2Bucket(): string | undefined {
    return process.env.R2_BUCKET || undefined;
  },
  get r2PublicUrl(): string | undefined {
    return process.env.R2_PUBLIC_URL || undefined;
  },
  get agentApiUrl(): string {
    return process.env.AGENT_API_URL || "http://localhost:8000";
  },
  /** Agent API 的可选内部密钥，与知识侧车密钥分开配置。 */
  get internalApiSecret(): string | undefined {
    return process.env.INTERNAL_API_SECRET || undefined;
  },
  /** 知识侧车的可选内部密钥。 */
  get lightragApiSecret(): string | undefined {
    return process.env.LIGHTRAG_API_SECRET || undefined;
  },
};

export function isSupabaseConfigured(): boolean {
  return Boolean(publicEnv.supabaseUrl && publicEnv.supabaseAnonKey);
}

export function isLiveKitConfigured(): boolean {
  return Boolean(
    serverEnv.livekitUrl &&
    serverEnv.livekitApiKey &&
    serverEnv.livekitApiSecret,
  );
}

export function isR2Configured(): boolean {
  return Boolean(
    serverEnv.r2AccountId &&
    serverEnv.r2AccessKeyId &&
    serverEnv.r2SecretAccessKey &&
    serverEnv.r2Bucket,
  );
}
