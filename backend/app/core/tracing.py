"""以本地 JSONL 记录追踪，可选同步到 Langfuse；记录失败不应中断业务。

配置优先级为显式覆盖、环境变量、默认值。ContextVar 隔离异步任务的追踪上下文，
提示词预览默认关闭，避免简历和职位资料进入日志。
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .logging import get_logger

log = get_logger(__name__)

# 显式配置覆盖环境变量，环境变量覆盖默认值。

_overrides: dict[str, Any] = {}
_langfuse_client: Any | None = None
_otel_tracer: Any | None = None
_write_lock = threading.Lock()


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def init_tracing(
    *,
    enabled: bool | None = None,
    trace_dir: str | Path | None = None,
    include_prompts: bool | None = None,
    langfuse_public_key: str | None = None,
    langfuse_secret_key: str | None = None,
    langfuse_host: str | None = None,
) -> None:
    """更新追踪配置并尝试初始化 Langfuse；传入 None 时保留原覆盖值。

    初始化失败不影响启动，显式配置优先于环境变量。
    """
    try:
        if enabled is not None:
            _overrides["enabled"] = bool(enabled)
        if trace_dir is not None:
            _overrides["dir"] = str(trace_dir)
        if include_prompts is not None:
            _overrides["include_prompts"] = bool(include_prompts)
        _init_langfuse(
            public_key=langfuse_public_key or os.environ.get("LANGFUSE_PUBLIC_KEY"),
            secret_key=langfuse_secret_key or os.environ.get("LANGFUSE_SECRET_KEY"),
            host=langfuse_host or os.environ.get("LANGFUSE_HOST"),
        )
    except Exception as exc:  # noqa: BLE001 - 追踪配置失败不能影响启动
        log.warning("tracing init failed (%s); continuing without tracing", exc)


def reset_tracing() -> None:
    """清除显式配置和 Langfuse 客户端，供测试隔离追踪状态。"""
    global _langfuse_client, _otel_tracer
    _overrides.clear()
    _langfuse_client = None
    _otel_tracer = None
    _current_trace.set(None)
    _span_stack.set(())


def is_enabled() -> bool:
    if "enabled" in _overrides:
        return bool(_overrides["enabled"])
    return _env_flag("TRACE_ENABLED", True)


def trace_dir() -> Path:
    raw = _overrides.get("dir") or os.environ.get("TRACE_DIR") or ".intervyn/traces"
    return Path(raw)


def _include_prompts() -> bool:
    if "include_prompts" in _overrides:
        return bool(_overrides["include_prompts"])
    return _env_flag("TRACE_INCLUDE_PROMPTS", False)


def _init_langfuse(*, public_key: str | None, secret_key: str | None, host: str | None) -> None:
    """尽力初始化可选 Langfuse 客户端，使 OTel 转发可用。"""
    global _langfuse_client
    if not (public_key and secret_key):
        return
    try:
        from langfuse import Langfuse  # 延迟加载 observability 可选扩展。
    except ImportError:
        log.debug("langfuse not installed; local JSONL tracing only")
        return
    try:
        kwargs: dict[str, Any] = {"public_key": public_key, "secret_key": secret_key}
        if host:
            kwargs["host"] = host
        _langfuse_client = Langfuse(**kwargs)
        log.info("Langfuse tracing enabled (local JSONL + hosted traces)")
    except Exception as exc:  # noqa: BLE001 - 远程追踪失败不影响业务
        log.warning("Langfuse init failed (%s); local JSONL tracing only", exc)
        _langfuse_client = None


def _otel() -> Any | None:
    """延迟获取 OTel 追踪器；缺少 SDK 或 Langfuse 时返回 None。"""
    global _otel_tracer
    if _otel_tracer is not None:
        return _otel_tracer
    if _langfuse_client is None:
        return None
    try:
        from opentelemetry import trace as otel_trace  # OTel 随 Langfuse 可选依赖提供。

        _otel_tracer = otel_trace.get_tracer("intervyn")
        return _otel_tracer
    except Exception:  # noqa: BLE001 - OTel 为可选集成
        return None


def langfuse_trace_url(trace_id: str) -> str | None:
    """生成远程追踪链接；未配置 Langfuse 时返回 None。"""
    if _langfuse_client is None:
        return None
    try:
        return _langfuse_client.get_trace_url(trace_id)
    except Exception:  # noqa: BLE001 - 仅用于展示追踪链接
        return None


# 异步任务通过 ContextVar 隔离追踪和 span 上下文。

_BORING_ATTRS = {"session_id"}


@dataclass
class _TraceInfo:
    trace_id: str
    name: str
    session_id: str | None
    start_ts: str
    start_perf: float


@dataclass
class _SpanInfo:
    span_id: str
    trace_id: str
    parent_id: str | None
    name: str
    start_perf: float
    otel_cm: Any | None = None
    otel_span: Any | None = None


_current_trace: ContextVar[_TraceInfo | None] = ContextVar("di_trace", default=None)
_span_stack: ContextVar[tuple[_SpanInfo, ...]] = ContextVar("di_spans", default=())


def current_trace_id() -> str | None:
    t = _current_trace.get()
    return t.trace_id if t is not None else None


def current_session_id() -> str | None:
    t = _current_trace.get()
    return t.session_id if t is not None else None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _new_trace_id() -> str:
    return "tr_" + uuid.uuid4().hex[:12]


def _new_span_id() -> str:
    return "sp_" + uuid.uuid4().hex[:8]


def _trace_path(trace_id: str, *, directory: Path | None = None) -> Path:
    return (directory or trace_dir()) / f"{trace_id}.jsonl"


def _append_event(event: dict[str, Any], *, directory: Path | None = None) -> None:
    """按需创建目录并追加一条 JSONL 事件，写入失败不影响业务。"""
    try:
        d = directory or trace_dir()
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, default=str)
        with _write_lock, open(d / f"{event['trace_id']}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:  # noqa: BLE001 - 追踪失败不能中断业务
        log.debug("tracing write failed (%s)", exc)


def _otel_start(name: str, attrs: dict[str, Any]) -> tuple[Any | None, Any | None]:
    """同步启动 OTel span；未启用或集成失败时返回 None。"""
    tracer = _otel()
    if tracer is None:
        return None, None
    try:
        cm = tracer.start_as_current_span(name)
        span = cm.__enter__()
        try:
            for k, v in attrs.items():
                span.set_attribute(k, str(v)[:500])
        except Exception:  # noqa: BLE001, S110 - 附加属性写入失败可忽略
            pass
        return cm, span
    except Exception:  # noqa: BLE001 - OTel 为可选集成
        return None, None


def _otel_end(cm: Any | None, span: Any | None, *, status: str, error: str | None) -> None:
    if cm is None:
        return
    try:
        if span is not None and error:
            try:
                span.set_attribute("error", error[:500])
            except Exception:  # noqa: BLE001, S110 - 附加信息写入失败可忽略
                pass
        cm.__exit__(None, None, None)
    except Exception as exc:  # noqa: BLE001 - OTel 为可选集成
        log.debug("otel span close failed (%s)", exc)


@contextlib.contextmanager
def start_trace(
    name: str, *, session_id: str | None = None, metadata: dict[str, Any] | None = None
) -> Iterator[str]:
    """上下文管理器产出追踪 ID；嵌套时复用外层追踪，禁用时产出占位 ID 且不写事件。"""
    if not is_enabled():
        yield "tr_disabled"
        return
    outer = _current_trace.get()
    if outer is not None:
        # 嵌套调用复用外层追踪，避免把一次流程拆成多个独立追踪。
        yield outer.trace_id
        return
    trace_id = _new_trace_id()
    info = _TraceInfo(
        trace_id=trace_id,
        name=name,
        session_id=session_id,
        start_ts=_utc_now(),
        start_perf=time.perf_counter(),
    )
    token = _current_trace.set(info)
    _append_event(
        {
            "type": "trace_start",
            "trace_id": trace_id,
            "name": name,
            "session_id": session_id,
            "ts": info.start_ts,
            "metadata": metadata or {},
        }
    )
    status, error = "ok", None
    try:
        yield trace_id
    except Exception as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = (time.perf_counter() - info.start_perf) * 1000
        _append_event(
            {
                "type": "trace_end",
                "trace_id": trace_id,
                "name": name,
                "session_id": session_id,
                "ts": _utc_now(),
                "duration_ms": round(duration_ms, 1),
                "status": status,
                **({"error": error[:500]} if error else {}),
            }
        )
        try:
            _current_trace.reset(token)
        except ValueError:
            # 关闭回调可能运行在另一异步上下文，无法重置原 ContextVar 令牌。
            # 仅清除继承的同一追踪，避免打断收尾或覆盖另一个活跃追踪。
            if _current_trace.get() is info:
                _current_trace.set(outer)


@contextlib.contextmanager
def start_span(name: str, **attrs: Any) -> Iterator[str]:
    """在当前追踪内创建 span 并产出其 ID；无追踪时自动创建，禁用时不写事件。"""
    if not is_enabled():
        yield "sp_disabled"
        return
    if _current_trace.get() is None:
        with start_trace("auto"), start_span(name, **attrs) as span_id:
            yield span_id
        return
    trace = _current_trace.get()
    assert trace is not None
    stack = _span_stack.get()
    parent_id = stack[-1].span_id if stack else None
    span_id = _new_span_id()
    otel_cm, otel_span = _otel_start(name, {"trace_id": trace.trace_id, **attrs})
    info = _SpanInfo(
        span_id=span_id,
        trace_id=trace.trace_id,
        parent_id=parent_id,
        name=name,
        start_perf=time.perf_counter(),
        otel_cm=otel_cm,
        otel_span=otel_span,
    )
    token = _span_stack.set(stack + (info,))
    _append_event(
        {
            "type": "span_start",
            "trace_id": trace.trace_id,
            "span_id": span_id,
            "parent_id": parent_id,
            "name": name,
            "ts": _utc_now(),
            "attrs": attrs,
        }
    )
    status, error = "ok", None
    try:
        yield span_id
    except Exception as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = (time.perf_counter() - info.start_perf) * 1000
        _append_event(
            {
                "type": "span_end",
                "trace_id": trace.trace_id,
                "span_id": span_id,
                "name": name,
                "ts": _utc_now(),
                "duration_ms": round(duration_ms, 1),
                "status": status,
                **({"error": error[:500]} if error else {}),
            }
        )
        _otel_end(otel_cm, otel_span, status=status, error=error)
        _span_stack.reset(token)


def add_event(name: str, attrs: dict[str, Any] | None = None) -> None:
    """向当前追踪或 span 添加即时事件；追踪禁用或无活动上下文时跳过。"""
    if not is_enabled():
        return
    trace = _current_trace.get()
    if trace is None:
        return
    stack = _span_stack.get()
    try:
        _append_event(
            {
                "type": "event",
                "trace_id": trace.trace_id,
                "span_id": stack[-1].span_id if stack else None,
                "name": name,
                "ts": _utc_now(),
                "attrs": attrs or {},
            }
        )
    except Exception:  # noqa: BLE001, S110 - 追踪失败不能中断业务
        pass


def record_llm_call(
    *,
    provider: str,
    model: str,
    method: str,
    schema: str = "",
    prompt_chars: int = 0,
    latency_ms: float = 0.0,
    ok: bool = True,
    error: str | None = None,
    prompt_preview: str = "",
) -> None:
    """记录模型调用长度；仅显式开启时保存截断的提示词预览。"""
    if not is_enabled():
        return
    trace = _current_trace.get()
    if trace is None:
        return
    stack = _span_stack.get()
    try:
        event: dict[str, Any] = {
            "type": "llm_call",
            "trace_id": trace.trace_id,
            "span_id": stack[-1].span_id if stack else None,
            "ts": _utc_now(),
            "provider": provider,
            "model": model,
            "method": method,
            "schema": schema,
            "prompt_chars": prompt_chars,
            "latency_ms": round(latency_ms, 1),
            "ok": ok,
        }
        if error:
            event["error"] = error[:500]
        if prompt_preview and _include_prompts():
            event["prompt_preview"] = prompt_preview[:500]
        _append_event(event)
    except Exception:  # noqa: BLE001, S110 - 追踪失败不能中断业务
        pass


def traced(name: str | None = None):
    """将异步流程函数包裹在指定名称的 span 内。"""

    def deco(fn):
        span_name = name or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with start_span(span_name):
                return await fn(*args, **kwargs)

        return wrapper

    return deco


# 模型适配器包装。


class TracedLLM:
    """代理模型适配器并记录耗时和结果，包括离线模拟调用。

    仅显式启用提示词记录时保存截断预览，不保存完整提示词。
    """

    def __init__(self, inner: Any, *, provider: str = "") -> None:
        self._inner = inner
        self._provider = provider or type(inner).__name__.replace("LLM", "").lower() or "mock"
        self._model = getattr(inner, "_model", "") or ""

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def complete_text(self, *, system: str, user: str) -> str:
        t0 = time.perf_counter()
        with start_span("llm.complete_text", provider=self._provider, model=self._model):
            try:
                result = await self._inner.complete_text(system=system, user=user)
            except Exception as exc:
                record_llm_call(
                    provider=self._provider,
                    model=self._model,
                    method="complete_text",
                    prompt_chars=len(system) + len(user),
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                    prompt_preview=f"{system}\n{user}",
                )
                raise
            record_llm_call(
                provider=self._provider,
                model=self._model,
                method="complete_text",
                prompt_chars=len(system) + len(user),
                latency_ms=(time.perf_counter() - t0) * 1000,
                ok=True,
                prompt_preview=f"{system}\n{user}",
            )
            return result

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        schema_name = getattr(schema, "__name__", str(schema))
        t0 = time.perf_counter()
        with start_span(
            "llm.complete_json",
            provider=self._provider,
            model=self._model,
            schema=schema_name,
        ):
            try:
                result = await self._inner.complete_json(system=system, user=user, schema=schema)
            except Exception as exc:
                record_llm_call(
                    provider=self._provider,
                    model=self._model,
                    method="complete_json",
                    schema=schema_name,
                    prompt_chars=len(system) + len(user),
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                    prompt_preview=f"{system}\n{user}",
                )
                raise
            record_llm_call(
                provider=self._provider,
                model=self._model,
                method="complete_json",
                schema=schema_name,
                prompt_chars=len(system) + len(user),
                latency_ms=(time.perf_counter() - t0) * 1000,
                ok=True,
                prompt_preview=f"{system}\n{user}",
            )
            return result


# CLI 与 API 共用追踪读取逻辑。


@dataclass
class TraceSummary:
    trace_id: str
    name: str
    session_id: str | None
    started_at: str
    duration_ms: float | None
    spans: int
    llm_calls: int
    errors: int
    status: str


def _iter_events(trace_id: str, *, directory: Path | None = None) -> Iterator[dict[str, Any]]:
    path = _trace_path(trace_id, directory=directory)
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def read_trace(trace_id: str, *, directory: Path | None = None) -> dict[str, Any] | None:
    """读取事件并组装嵌套 span；标识无效、文件缺失或无可解析事件时返回 None。"""
    if not trace_id or "/" in trace_id or trace_id.startswith("."):
        return None
    events = list(_iter_events(trace_id, directory=directory))
    if not events:
        return None
    summary = summarize_events(trace_id, events)
    spans: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for ev in events:
        if ev.get("type") == "span_start":
            spans[ev["span_id"]] = {
                "span_id": ev["span_id"],
                "parent_id": ev.get("parent_id"),
                "name": ev.get("name"),
                "started_at": ev.get("ts"),
                "attrs": ev.get("attrs", {}),
                "events": [],
                "llm_calls": [],
                "duration_ms": None,
                "status": "running",
            }
            order.append(ev["span_id"])
        elif ev.get("type") == "span_end" and ev.get("span_id") in spans:
            spans[ev["span_id"]].update(
                duration_ms=ev.get("duration_ms"),
                status=ev.get("status", "ok"),
                **({"error": ev["error"]} if ev.get("error") else {}),
            )
        elif ev.get("type") in {"event", "llm_call"}:
            sid = ev.get("span_id")
            if sid in spans:
                key = "llm_calls" if ev["type"] == "llm_call" else "events"
                spans[sid][key].append(ev)
    children: dict[str | None, list[dict[str, Any]]] = {}
    for sid in order:
        children.setdefault(spans[sid]["parent_id"], []).append(spans[sid])
    summary["spans"] = children.get(None, [])
    summary["all_spans_flat"] = [spans[sid] for sid in order]
    summary["events"] = [e for e in events if e.get("type") == "event" and not e.get("span_id")]
    summary["langfuse_url"] = langfuse_trace_url(trace_id)
    return summary


def summarize_events(trace_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """从事件聚合追踪摘要，供列表和详情共用。"""
    name, session_id, started_at = trace_id, None, ""
    duration_ms: float | None = None
    status = "running"
    spans = llm_calls = errors = 0
    for ev in events:
        t = ev.get("type")
        if t == "trace_start":
            name = ev.get("name", name)
            session_id = ev.get("session_id")
            started_at = ev.get("ts", "")
        elif t == "trace_end":
            duration_ms = ev.get("duration_ms")
            status = ev.get("status", "ok")
            if ev.get("error"):
                errors += 1
        elif t == "span_start":
            spans += 1
        elif t == "span_end" and ev.get("status") == "error":
            errors += 1
        elif t == "llm_call":
            llm_calls += 1
            if not ev.get("ok", True):
                errors += 1
    return {
        "trace_id": trace_id,
        "name": name,
        "session_id": session_id,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "spans": spans,
        "llm_calls": llm_calls,
        "errors": errors,
        "status": status,
    }


def list_traces(
    *, directory: Path | None = None, session_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """限量读取并按文件修改时间倒序列出摘要，跳过无效文件。"""
    d = directory or trace_dir()
    if not d.exists():
        return []
    try:
        files = sorted(d.glob("tr_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                events = [json.loads(line) for line in fh if line.strip()]
        except (OSError, json.JSONDecodeError):
            continue
        header = summarize_events(path.stem, events)
        if session_id and header["session_id"] != session_id:
            continue
        header["langfuse_url"] = None  # 列表只聚合本地摘要，远程链接在详情读取时再生成。
        out.append(header)
        if len(out) >= max(1, limit):
            break
    return out


__all__ = [
    "TracedLLM",
    "add_event",
    "current_session_id",
    "current_trace_id",
    "init_tracing",
    "is_enabled",
    "langfuse_trace_url",
    "list_traces",
    "read_trace",
    "record_llm_call",
    "reset_tracing",
    "start_span",
    "start_trace",
    "trace_dir",
    "traced",
]
