"""不联网的确定性模拟适配器，可在没有密钥或提供方 SDK 时运行。

结构化输出递归填充必填字段；列表至少包含一个元素，本地化字典提供 en 回退键。
"""

from __future__ import annotations

import hashlib
import struct
import types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

_NoneType = type(None)


def _unwrap_optional(annotation: Any) -> Any:
    """剥离两种 Optional 写法中的 None，保留实际值类型。"""
    origin = get_origin(annotation)
    # 兼容 PEP 604 的 X | None 和 typing.Optional 的不同运行时表示。
    if origin is Union or origin is types.UnionType:
        non_null = [a for a in get_args(annotation) if a is not _NoneType]
        if len(non_null) == 1:
            return non_null[0]
    return annotation


def _build_value(annotation: Any) -> Any:
    """按类型递归构造满足共享模型约束的最小模拟值。"""
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if origin is Literal:
        return get_args(annotation)[0]

    if origin in (list, tuple, set, frozenset):
        args = get_args(annotation)
        elem = _build_value(args[0]) if args else "mock"
        return [elem]
    if origin is dict:
        # 本地化字典必须包含 en 回退键。
        return {"en": "mock"}

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return build_mock(annotation).model_dump()

    if annotation is bool:
        return False
    if annotation is int:
        return 1
    if annotation is float:
        return 0.5
    if annotation is str:
        return "mock"
    if annotation is dict:
        return {"en": "mock"}

    return "mock"


def build_mock(schema: type[BaseModel]) -> BaseModel:
    """仅填充必填字段，其余保留模型默认值；difficulty 固定为中间值 3。"""
    built: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        if name == "difficulty":
            built[name] = 3
            continue
        built[name] = _build_value(field.annotation)
    return schema.model_validate(built)


class MockLLM:
    """生成固定文本和契约有效的结构化模拟结果。"""

    async def complete_text(self, *, system: str, user: str) -> str:
        return "This is a deterministic mock completion."

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        return build_mock(schema)


class MockEmbeddings:
    """根据文本哈希生成固定的八维向量，保证跨运行一致。"""

    DIM = 8

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        floats: list[float] = []
        for i in range(self.DIM):
            chunk = digest[i * 4 : i * 4 + 4]
            (raw,) = struct.unpack(">I", chunk)
            floats.append(raw / 0xFFFFFFFF)
        return floats

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]
