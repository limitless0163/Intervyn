import { NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { gateRequest } from "@intervyn/ee";
import { presignUpload } from "@/lib/r2";
import { isR2Configured, isSupabaseConfigured } from "@/lib/env";
import { getUser } from "@/lib/supabase/server";
import { CV_CONTENT_TYPES, MAX_CV_BYTES } from "@/lib/cv-upload";

const BodySchema = z.object({
  filename: z.string().min(1),
  content_type: z.string().min(1),
  // 客户端报告的大小用于请求校验，并传入预签名上传请求。
  size: z.number().int().positive().max(MAX_CV_BYTES),
});

export async function POST(request: Request) {
  // 发放上传地址会产生存储成本：配置认证时要求登录，并应用发行版门控。
  const user = await getUser();
  if (isSupabaseConfigured() && !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const gate = gateRequest({
    pathname: "/api/upload",
    isAuthenticated: Boolean(user),
  });
  if (!gate.allow) {
    return NextResponse.json({ error: "Sign in required" }, { status: 401 });
  }

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 },
    );
  }

  const normalizedType = (body.content_type.split(";", 1)[0] ?? "")
    .trim()
    .toLowerCase();
  if (!CV_CONTENT_TYPES.has(normalizedType)) {
    return NextResponse.json(
      { error: "Unsupported file type. Upload a PDF, DOCX, or text CV." },
      { status: 415 },
    );
  }

  if (!isR2Configured()) {
    return NextResponse.json({ error: "R2 not configured" }, { status: 501 });
  }

  // 随机键降低简历地址被猜中的风险；去除文件名路径分隔符以避免改变键结构。
  const safeName = body.filename.replace(/[/\\]/g, "_").slice(0, 100);
  const key = `uploads/${randomUUID()}-${safeName}`;

  // 类型校验使用规范化值，上传请求保留客户端实际使用的 Content-Type。
  try {
    const result = await presignUpload(key, body.content_type, body.size);
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { error: "Upload could not be prepared" },
      { status: 503 },
    );
  }
}
