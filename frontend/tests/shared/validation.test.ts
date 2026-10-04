import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { SCHEMAS } from "../../packages/shared/src/index";
import cases from "../../packages/shared/fixtures/validation-cases.json";

const fixture: unknown = JSON.parse(
  readFileSync(
    new URL(
      "../../packages/shared/fixtures/interview-context.sample.json",
      import.meta.url,
    ),
    "utf8",
  ),
);

describe("shared wire validation corpus (also run by Pydantic)", () => {
  it.each(cases)("$name", (testCase) => {
    let base: unknown = fixture;
    for (const key of testCase.base_path?.split(".") ?? []) {
      base = (base as Record<string, unknown>)[key];
    }
    const payload: Record<string, unknown> = {
      ...(testCase.base_path
        ? structuredClone(base as Record<string, unknown>)
        : {}),
      ...testCase.set,
    };
    for (const key of testCase.remove ?? []) delete payload[key];
    const schema = SCHEMAS[testCase.schema];
    expect(schema, `Unregistered contract: ${testCase.schema}`).toBeDefined();
    const result = schema!.safeParse(payload);
    expect(result.success).toBe(testCase.valid);
    if (result.success && testCase.expected) {
      expect(result.data).toMatchObject(testCase.expected);
    }
  });
});
