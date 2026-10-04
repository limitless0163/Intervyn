# ruff: noqa: BLE001, S110, PYI034, PYI046
# 观测必须容错，可选提供方调用失败后继续；空实现保留提供方接口以兼容调用方。
"""初始化本地追踪及可选 Sentry/Langfuse，并导出业务调用所需的追踪接口。

缺少配置或可选依赖时跳过远程集成；观测失败不能中断准备、评分或语音轮次。
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from .logging import get_logger
from .tracing import init_tracing
from .tracing import start_span as _real_start_span

_log = get_logger("intervyn.observability")

_initialized = False


class _Settings(Protocol):
    """观测配置的结构化接口；缺少属性时通过 getattr 使用兼容默认值。"""


def _env(*names: str) -> str | None:
    for name in names:
        val = os.environ.get(name)
        if val:
            return val
    return None


def _sentry_dsn(settings: Any | None) -> str | None:
    return getattr(settings, "sentry_dsn", None) or _env("SENTRY_DSN")


def _langfuse_keys(settings: Any | None) -> tuple[str | None, str | None]:
    public = getattr(settings, "langfuse_public_key", None) or _env("LANGFUSE_PUBLIC_KEY")
    secret = getattr(settings, "langfuse_secret_key", None) or _env("LANGFUSE_SECRET_KEY")
    return public, secret


def init_observability(settings: Any | None = None) -> None:
    """同步本地追踪配置并按需初始化远程观测；可重复调用，缺少可选依赖时降级。"""
    global _initialized
    if _initialized:
        return
    _initialized = True  # 先标记已初始化，避免提供方失败时反复初始化。

    # 先同步本地配置，使 .env 中的追踪设置也能生效。
    try:
        init_tracing(
            enabled=getattr(settings, "trace_enabled", None),
            trace_dir=getattr(settings, "trace_dir", None),
            include_prompts=getattr(settings, "trace_include_prompts", None),
            langfuse_public_key=getattr(settings, "langfuse_public_key", None),
            langfuse_secret_key=getattr(settings, "langfuse_secret_key", None),
            langfuse_host=getattr(settings, "langfuse_host", None),
        )
    except Exception as exc:  # pragma: no cover - 防御性降级
        _log.warning("tracing init failed: %s", exc)

    dsn = _sentry_dsn(settings)
    if dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=dsn,
                traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                environment=os.environ.get("NODE_ENV", "production"),
            )
            _log.info("Sentry initialized")
        except ImportError:
            _log.debug("sentry-sdk not installed; skipping Sentry (extra: observability)")
        except Exception as exc:  # pragma: no cover - 防御性降级
            _log.warning("Sentry init failed: %s", exc)

    public, secret = _langfuse_keys(settings)
    if public and secret:
        try:
            import langfuse  # noqa: F401

            _log.info("Langfuse credentials present; hosted tracing enabled")
        except ImportError:
            _log.debug("langfuse not installed; skipping (extra: observability)")
        except Exception as exc:  # pragma: no cover - 防御性降级
            _log.warning("Langfuse init failed: %s", exc)


class _NoOpTracer:
    """提供调用方所需的最小空追踪接口，不产生记录。"""

    def start_span(self, _name: str, **_kw: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpSpan:
    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def set_attribute(self, _key: str, _value: Any) -> None:
        return None


def get_tracer() -> Any:
    """返回支持 start_span 的追踪器；关闭追踪时仍可无条件进入上下文管理器。"""
    from . import tracing as _tracing

    class _Tracer:
        def start_span(self, name: str, **kw: Any) -> Any:
            return _real_start_span(name, **kw)

    # 保留空实现供既有测试替换，默认使用实际追踪器。
    _ = _tracing
    return _Tracer()


def capture_error(error: BaseException) -> None:
    """尽力向 Sentry 上报异常，否则写日志；上报失败不影响业务。"""
    dsn = _sentry_dsn(None)
    if dsn:
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(error)
            return
        except ImportError:
            pass
        except Exception:  # pragma: no cover - 防御性降级
            pass
    _log.error("capture_error: %r", error)
