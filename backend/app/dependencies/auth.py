"""可选内部密钥校验；配置 INTERNAL_API_SECRET 后要求请求携带匹配的请求头。

未配置时保持本地免鉴权行为，此依赖不提供用户身份或会话所有权校验。
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from ..core.config import get_settings

__all__ = ["require_internal_secret"]


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """使用恒定时间比较校验内部密钥；缺失或不匹配时返回 401。"""
    expected = get_settings().internal_api_secret
    if not expected:
        return  # 未配置密钥时保持开源版默认行为。
    if not x_internal_secret or not hmac.compare_digest(
        x_internal_secret.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing internal secret"
        )
