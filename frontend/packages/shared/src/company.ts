import { z } from "zod";

export const CitationSchema = z.object({
  title: z.string(),
  url: z.string(),
  snippet: z.string().nullable().default(null),
});
export type Citation = z.infer<typeof CitationSchema>;

export const CompanyIntelSchema = z.object({
  name: z.string(),
  summary: z.string(),
  industry: z.string().nullable().default(null),
  tech_stack: z.array(z.string()),
  values: z.array(z.string()),
  interview_process: z.array(z.string()),
  recent_news: z.array(z.string()),
  sources: z.array(CitationSchema).default([]),
  research_status: z.enum(["complete", "unavailable"]).default("unavailable"),
  research_error: z
    .enum([
      "not_configured",
      "unsupported_provider",
      "no_sources",
      "timeout",
      "request_failed",
      "invalid_company",
      "invalid_response",
    ])
    .nullable()
    .default(null),
  search_suggestions: z.string().nullable().default(null),
});
export type CompanyIntel = z.infer<typeof CompanyIntelSchema>;
