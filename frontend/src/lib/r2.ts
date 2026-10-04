import "server-only";
import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { isR2Configured, serverEnv } from "@/lib/env";

export interface PresignedUpload {
  /** 在有效期内将文件字节直接 PUT 到此地址。 */
  uploadUrl: string;
  /** 对象读取地址；可访问性依赖存储桶或公共域名配置。 */
  publicUrl: string;
}

let cachedClient: S3Client | null = null;

function r2Client(): S3Client {
  if (cachedClient) return cachedClient;
  cachedClient = new S3Client({
    region: "auto",
    endpoint: `https://${serverEnv.r2AccountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: serverEnv.r2AccessKeyId as string,
      secretAccessKey: serverEnv.r2SecretAccessKey as string,
    },
  });
  return cachedClient;
}

/**
 * 为对象签发十分钟有效的上传地址；缺少 R2 配置时抛出异常。
 * contentLength 可选，以字节计；调用方应先校验上传类型和大小。
 */
export async function presignUpload(
  key: string,
  contentType: string,
  contentLength?: number,
): Promise<PresignedUpload> {
  if (!isR2Configured()) {
    throw new Error(
      "R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET.",
    );
  }

  // 将获准类型与可选长度传入预签名请求，客户端上传需使用相同请求参数。
  const command = new PutObjectCommand({
    Bucket: serverEnv.r2Bucket,
    Key: key,
    ContentType: contentType,
    ContentLength: contentLength,
  });

  const uploadUrl = await getSignedUrl(r2Client(), command, { expiresIn: 600 });

  const base =
    serverEnv.r2PublicUrl?.replace(/\/$/, "") ||
    `https://${serverEnv.r2AccountId}.r2.cloudflarestorage.com/${serverEnv.r2Bucket}`;
  const publicUrl = `${base}/${key}`;

  return { uploadUrl, publicUrl };
}
