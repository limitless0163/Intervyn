"""将粘贴文本、data URL 或远程简历文档转换为正文，避免将二进制内容送入分析。

优先使用 markitdown；仅配置 Gemini 提供方及密钥时尝试多模态兜底。
转换失败通过空正文或警告降级；远程文件读取失败保留原地址供后续校验。
"""

from __future__ import annotations

import asyncio
import base64
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ...core.logging import get_logger
from ...utils.validation import assess_text

if TYPE_CHECKING:
    from ...dependencies.container import Deps

__all__ = ["extract_cv_text"]

log = get_logger(__name__)

# 限制文件读取等待时间，避免不可达主机长时间阻塞准备。
_CV_FETCH_TIMEOUT_SEC = 5.0
_MAX_DOCUMENT_BYTES = 10_000_000
_MAX_EXTRACTED_CHARS = 200_000
_CONVERSION_TIMEOUT_SEC = 20.0

_MIN_CV_LEN = 30

_UNREADABLE_WARNING = (
    "Couldn't read the uploaded CV file — proceeding with limited candidate info."
)

# markitdown 按文件后缀选择转换器，因此从 MIME 映射后缀。
_MIME_SUFFIX = {
    "application/pdf": ".pdf",
    "application/x-pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
}

# 要求仅输出文档正文，避免说明文字混入简历分析。
_GEMINI_PROMPT = (
    "Extract the full plain-text content of this résumé/CV. "
    "Output only the text, no commentary."
)


def _suffix_for_mime(mime: str) -> str:
    """按 MIME 选择转换器所需的后缀，未知类型使用 .txt。"""
    base = (mime or "").split(";", 1)[0].strip().lower()
    return _MIME_SUFFIX.get(base, ".txt")


def _is_meaningful(text: str) -> bool:
    """复用准备输入校验，判断提取正文是否具有有效简历内容。"""
    ok, _ = assess_text(text, kind="cv", min_len=_MIN_CV_LEN)
    return ok


def _markitdown_extract(data: bytes, mime: str) -> str:
    """将字节写入带 MIME 后缀的临时文件，交由延迟导入的 markitdown 转换。

    此方法会阻塞，调用方需放在线程执行；失败时返回空字符串。
    """
    try:
        from markitdown import MarkItDown
    except ImportError as exc:  # pragma: no cover - 依赖可选文档转换库
        log.warning("markitdown is not installed; cannot parse CV document (%s)", exc)
        return ""

    suffix = _suffix_for_mime(mime)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        result = MarkItDown().convert(tmp_path)
        return (result.text_content or "").strip()
    except Exception as exc:  # noqa: BLE001 - 转换失败时返回空正文
        log.warning("markitdown conversion failed (%s)", type(exc).__name__)
        return ""
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:  # pragma: no cover - 临时文件清理失败不影响业务
                pass


async def _gemini_extract(data: bytes, mime: str, deps: Deps) -> str:
    """用延迟导入的 Gemini 多模态接口提取文档正文，供本地转换失败时兜底。

    提供方调用失败时返回空字符串。
    """
    settings = deps.settings
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - 依赖可选 SDK
        log.warning("google-genai is not installed; skipping Gemini CV fallback (%s)", exc)
        return ""

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[
                        types.Part.from_bytes(data=data, mime_type=mime or "application/pdf"),
                        _GEMINI_PROMPT,
                    ],
                ),
                timeout=settings.llm_call_timeout_sec,
            )
            return (resp.text or "").strip()
        finally:
            await client.aio.aclose()
            client.close()
    except Exception as exc:  # noqa: BLE001 - 模型提取失败时返回空正文
        log.warning("Gemini CV extraction failed (%s)", type(exc).__name__)
        return ""


def _decode_data_url(cv_url: str) -> tuple[bytes, str] | None:
    """将 base64 或百分号编码的 data URL 解码为 (bytes, mime)，无效时返回 None。"""
    if not cv_url.startswith("data:"):
        return None
    try:
        header, _, payload = cv_url[len("data:") :].partition(",")
        if not payload:
            return None
        meta = header.split(";")
        mime = meta[0] if meta and meta[0] else "application/octet-stream"
        is_base64 = "base64" in meta[1:]
        if is_base64:
            data = base64.b64decode(payload, validate=False)
        else:
            # 兼容百分号编码的文本 data URL。
            from urllib.parse import unquote_to_bytes

            data = unquote_to_bytes(payload)
        return data, mime
    except Exception as exc:  # noqa: BLE001 - 无效 data URL 不作为文档解析
        log.warning("could not decode data: CV URL (%s)", exc)
        return None


def _is_fetchable_url(url: str) -> bool:
    """仅允许 HTTP(S)，拒绝本地主机及私有、回环等非公网 IP 字面量。

    不解析域名 DNS；完整防护仍依赖网络出口限制。拒绝时按读取失败降级。
    """
    import ipaddress
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if parts.username is not None or parts.password is not None:
        return False
    host = (parts.hostname or "").strip("[]").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".internal")):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True  # 普通域名只校验字面量，不解析 DNS，限制见函数说明。
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


# 逐跳重新校验目标，并限制手动重定向次数。
_MAX_CV_REDIRECTS = 5


async def _fetch_url_bytes(cv_url: str) -> tuple[bytes, str] | None:
    """读取文件并返回 (bytes, content_type)，失败返回 None。

    手动跟随有限次重定向并逐跳校验目标，避免公网 URL 跳转内网后绕过检查。
    """
    if not _is_fetchable_url(cv_url):
        log.warning("fetch_cv: refusing non-public URL")
        return None
    try:
        async with asyncio.timeout(_CV_FETCH_TIMEOUT_SEC):
            async with httpx.AsyncClient(timeout=_CV_FETCH_TIMEOUT_SEC) as client:
                url = cv_url
                for _ in range(_MAX_CV_REDIRECTS + 1):
                    async with client.stream("GET", url, follow_redirects=False) as resp:
                        if resp.is_redirect:
                            location = resp.headers.get("location")
                            if not location:
                                return None
                            nxt = str(resp.url.join(location))
                            if not _is_fetchable_url(nxt):
                                log.warning("fetch_cv: refusing redirect to non-public URL")
                                return None
                            url = nxt
                            continue
                        resp.raise_for_status()
                        length = resp.headers.get("content-length")
                        if length and int(length) > _MAX_DOCUMENT_BYTES:
                            return None
                        data = bytearray()
                        async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                            data.extend(chunk)
                            if len(data) > _MAX_DOCUMENT_BYTES:
                                return None
                        return bytes(data), resp.headers.get("content-type", "")
                log.warning("fetch_cv: too many redirects")
                return None
    except Exception as exc:  # noqa: BLE001 - 读取失败由调用方降级
        # 简历地址可能包含签名令牌，异常也可能带出 URL；只记录错误类型。
        log.warning("fetch_cv: remote read failed (%s)", type(exc).__name__)
        return None


def _bounded_text(text: str) -> tuple[str, list[str]]:
    if len(text) > _MAX_EXTRACTED_CHARS:
        return text[:_MAX_EXTRACTED_CHARS], ["CV text was truncated because the document is too large."]
    return text, []


async def _extract_from_bytes(data: bytes, mime: str, deps: Deps) -> tuple[str, list[str]]:
    """先用 markitdown，必要时用 Gemini；返回 (text, warnings)，全失败时正文为空。

    不把原始字节或 base64 作为简历正文交给分析。
    """
    if len(data) > _MAX_DOCUMENT_BYTES:
        return "", [_UNREADABLE_WARNING]
    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(_markitdown_extract, data, mime), timeout=_CONVERSION_TIMEOUT_SEC
        )
    except TimeoutError:
        log.warning("CV document conversion timed out")
        text = ""
    if text and _is_meaningful(text):
        return _bounded_text(text)

    # 扫描件等本地解析困难的文档可由多模态模型兜底。
    settings = deps.settings
    gemini_ready = bool(settings.gemini_api_key) and (
        (settings.llm_provider or "").lower() == "gemini"
    )
    if gemini_ready:
        fallback = await _gemini_extract(data, mime, deps)
        if fallback and _is_meaningful(fallback):
            return _bounded_text(fallback)

    # 本地提取结果未达到有效性阈值时仍优于空正文，由下游输入校验最终判断。
    if text:
        return _bounded_text(text)

    return "", [_UNREADABLE_WARNING]


async def extract_cv_text(cv_url: str, deps: Deps) -> tuple[str, list[str]]:
    """返回 (text, warnings)：粘贴文本原样返回，data URL 解码后解析，HTTP(S) 文件读取后解析。

    远程读取失败时保留原 URL 且不追加警告，以兼容离线流程；
    远程内容解析为空时保留原 URL 和解析警告。
    """
    if not cv_url:
        return "", []

    decoded = _decode_data_url(cv_url)
    if decoded is not None:
        data, mime = decoded
        return await _extract_from_bytes(data, mime, deps)
    if cv_url.lstrip().startswith("data:"):
        return "", [_UNREADABLE_WARNING]

    stripped = cv_url.strip()
    if stripped.lower().startswith(("http://", "https://")) and "\n" not in stripped:
        fetched = await _fetch_url_bytes(stripped)
        if fetched is None:
            # 读取失败保留 URL，兼容离线输入，不追加解析警告。
            return cv_url, []
        data, content_type = fetched
        text, warnings = await _extract_from_bytes(data, content_type, deps)
        if text:
            return text, warnings
        # 文档解析失败时保留 URL，同时返回解析警告。
        return cv_url, warnings

    return _bounded_text(cv_url)
