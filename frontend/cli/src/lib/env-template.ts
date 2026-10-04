/** 纯函数形式解析和渲染环境模板，便于在不访问终端或文件系统的情况下验证向导。 */

const KEY_LINE = /^(\s*)([A-Z][A-Z0-9_]*)=(.*)$/;

function unquote(value: string): string {
  if (
    value.length >= 2 &&
    ((value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'")))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

/** 解析简单 KEY=VALUE 行并去除外层引号；不展开变量或执行 Shell 表达式。 */
export function parseEnv(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    if (!/^[A-Z][A-Z0-9_]*$/.test(key)) continue;
    out[key] = unquote(line.slice(eq + 1).trim());
  }
  return out;
}

/** 为包含空白、# 或引号的值加引号，并转义双引号和反斜杠。 */
export function formatValue(value: string): string {
  if (value === "") return "";
  if (/[\s#"']/.test(value)) return `"${value.replace(/(["\\])/g, "\\$1")}"`;
  return value;
}

/**
 * 覆盖模板中指定键的值，保留原注释、顺序和空行；未提供的键沿用模板默认值。
 * 模板外的键追加到末尾，避免丢弃调用方配置。
 */
export function renderEnv(
  template: string,
  values: Record<string, string>,
): string {
  const seen = new Set<string>();
  const lines = template.split(/\r?\n/).map((raw) => {
    const match = raw.match(KEY_LINE);
    if (!match) return raw;
    const indent = match[1] ?? "";
    const key = match[2];
    if (key === undefined) return raw;
    seen.add(key);
    if (Object.prototype.hasOwnProperty.call(values, key)) {
      return `${indent}${key}=${formatValue(values[key] ?? "")}`;
    }
    return raw;
  });

  const extras = Object.keys(values).filter((key) => !seen.has(key));
  if (extras.length > 0) {
    lines.push("");
    lines.push("# Added by `intervyn init` (keys not in .env.example):");
    for (const key of extras)
      lines.push(`${key}=${formatValue(values[key] ?? "")}`);
  }
  return lines.join("\n");
}
