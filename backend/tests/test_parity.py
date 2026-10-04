"""将 Zod 与 Pydantic 的 JSON Schema 归一化为字段名、粗粒度类型及必填性并比对。

解析引用并兼容可空表示；共享 schema 目录为空时跳过。此检查不覆盖全部校验约束。
"""

import json
from pathlib import Path

import pytest

from app.schemas.shared_models import MODELS

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "frontend/packages/shared/schema"


def _defs(schema: dict) -> dict:
    defs = {}
    defs.update(schema.get("$defs", {}) or {})
    defs.update(schema.get("definitions", {}) or {})
    return defs


def _resolve(node: dict, defs: dict) -> dict:
    """沿本地 $ref 链取得实际节点。"""
    seen = set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            break
        seen.add(ref)
        key = ref.split("/")[-1]
        node = defs.get(key, {})
    return node


def _type_category(node: dict, defs: dict):
    node = _resolve(node, defs)

    branches = node.get("anyOf") or node.get("oneOf")
    if branches:
        non_null = []
        for branch in branches:
            resolved = _resolve(branch, defs)
            if resolved.get("type") != "null":
                non_null.append(resolved)
        if len(non_null) == 1:
            return _type_category(non_null[0], defs)
        return "union"

    node_type = node.get("type")
    # 兼容 anyOf 与 type 数组两种可空表示，统一取非 null 类型再比较。
    if isinstance(node_type, list):
        non_null = [t for t in node_type if t != "null"]
        if len(non_null) == 1:
            node_type = non_null[0]
        else:
            return "union"

    if "enum" in node:
        return ("enum", frozenset(node["enum"]))

    if node_type == "array":
        return "array"
    if node_type in ("integer", "number"):
        return "number"
    if node_type == "object" or "properties" in node or "additionalProperties" in node:
        return "object"
    return node_type


def _normalize(schema: dict) -> dict:
    defs = _defs(schema)
    root = _resolve(schema, defs)
    props = root.get("properties", {}) or {}
    required = set(root.get("required", []) or [])
    out = {}
    for field, node in props.items():
        out[field] = (_type_category(node, defs), field in required)
    return out


_SCHEMAS_PRESENT = SCHEMA_DIR.exists() and any(SCHEMA_DIR.glob("*.json"))


@pytest.mark.skipif(
    not _SCHEMAS_PRESENT,
    reason="Zod JSON Schemas not generated; run `pnpm --dir frontend --filter @intervyn/shared gen:schema`",
)
@pytest.mark.parametrize("name", list(MODELS.keys()))
def test_schema_parity(name: str) -> None:
    model = MODELS[name]
    zod_path = SCHEMA_DIR / f"{name}.json"
    assert zod_path.exists(), f"Missing generated Zod schema for {name}: {zod_path}"

    zod_schema = json.loads(zod_path.read_text(encoding="utf-8"))
    pyd_schema = model.model_json_schema()

    zod_norm = _normalize(zod_schema)
    pyd_norm = _normalize(pyd_schema)

    differing = sorted(
        set(zod_norm) ^ set(pyd_norm)
        | {k for k in (set(zod_norm) & set(pyd_norm)) if zod_norm[k] != pyd_norm[k]}
    )
    assert zod_norm == pyd_norm, (
        f"Schema parity mismatch for {name} on fields {differing}:\n"
        f"  zod={ {k: zod_norm.get(k) for k in differing} }\n"
        f"  pydantic={ {k: pyd_norm.get(k) for k in differing} }"
    )


@pytest.mark.skipif(
    not _SCHEMAS_PRESENT,
    reason="Zod JSON Schemas not generated; run `pnpm --dir frontend --filter @intervyn/shared gen:schema`",
)
def test_every_generated_schema_has_a_pydantic_mirror() -> None:
    """反向检查生成的每个 TS 契约都有 Pydantic 镜像，避免新增契约逃过正向遍历。"""
    generated = {p.stem for p in SCHEMA_DIR.glob("*.json")}
    registered = set(MODELS)
    missing_mirror = sorted(generated - registered)
    stale_entries = sorted(registered - generated)
    assert not missing_mirror, (
        f"Generated Zod schemas with no Pydantic mirror in MODELS: {missing_mirror}"
    )
    assert not stale_entries, (
        f"MODELS entries with no generated Zod schema: {stale_entries}"
    )
