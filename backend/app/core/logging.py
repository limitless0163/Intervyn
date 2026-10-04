"""统一初始化标准库日志，供后端各模块获取具名日志器。"""

from __future__ import annotations

import logging

_CONFIGURED = False


def _ensure_configured() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """初始化全局日志配置并返回具名日志器。"""
    _ensure_configured()
    return logging.getLogger(name)
