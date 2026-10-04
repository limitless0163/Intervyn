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

# Keep the document fetch tight so an unreachable host fails fast offline.
_CV_FETCH_TIMEOUT_SEC = 5.0

# Minimum length for an extraction to count as "meaningful" content.
_MIN_CV_LEN = 30

_UNREADABLE_WARNING = (
    "Couldn't read the uploaded CV file — proceeding with limited candidate info."
)

# Map common document MIME types to the file suffix markitdown keys conversion on.
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

# Gemini extraction prompt: text only, no commentary, so it round-trips cleanly.
_GEMINI_PROMPT = (
    "Extract the full plain-text content of this résumé/CV. "
    "Output only the text, no commentary."
)


def _suffix_for_mime(mime: str) -> str:
    """Best file suffix for ``mime`` (defaults to ``.txt`` for unknown types)."""
    base = (mime or "").split(";", 1)[0].strip().lower()
    return _MIME_SUFFIX.get(base, ".txt")


def _is_meaningful(text: str) -> bool:
    """True if ``text`` reads like real CV content (reuses the prep heuristics)."""
    ok, _ = assess_text(text, kind="cv", min_len=_MIN_CV_LEN)
    return ok


def _markitdown_extract(data: bytes, mime: str) -> str:
    """Convert document ``data`` to text via markitdown (blocking; run in a thread).

    Lazy-imports markitdown so the module imports without it installed. Writes the
    bytes to a temp file with a mime-derived suffix (markitdown dispatches on the
    extension) and returns the converted text, or ``""`` on any failure.
    """
    try:
        from markitdown import MarkItDown
    except ImportError as exc:  # pragma: no cover - depends on optional dep
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
    except Exception as exc:  # noqa: BLE001 - best-effort: any failure -> empty
        log.warning("markitdown conversion failed (%s)", exc)
        return ""
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:  # pragma: no cover - cleanup is advisory only
                pass


async def _gemini_extract(data: bytes, mime: str, deps: Deps) -> str:
    """Extract CV text from raw bytes via Gemini native multimodal (lazy import).

    Used only as a fallback when markitdown yields nothing (e.g. scanned/image
    PDFs). Returns ``""`` on any failure so the caller degrades gracefully.
    """
    settings = deps.settings
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on optional SDK
        log.warning("google-genai is not installed; skipping Gemini CV fallback (%s)", exc)
        return ""

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=data, mime_type=mime or "application/pdf"),
                _GEMINI_PROMPT,
            ],
        )
        return (resp.text or "").strip()
    except Exception as exc:  # noqa: BLE001 - best-effort: any failure -> empty
        log.warning("Gemini CV extraction failed (%s)", exc)
        return ""


def _decode_data_url(cv_url: str) -> tuple[bytes, str] | None:
    """Decode a ``data:<mime>;base64,<b64>`` URL to ``(bytes, mime)``; else ``None``."""
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
            # Percent-encoded text data URL (rare for CVs, but handle it).
            from urllib.parse import unquote_to_bytes

            data = unquote_to_bytes(payload)
        return data, mime
    except Exception as exc:  # noqa: BLE001 - malformed data URL -> not a document
        log.warning("could not decode data: CV URL (%s)", exc)
        return None


def _is_fetchable_url(url: str) -> bool:
    """SSRF guard for the user-supplied CV URL.

    Only http(s), and never loopback/private/link-local hosts — the fetch runs
    server-side, so an attacker-chosen URL could otherwise probe the internal
    network (e.g. a metadata service or the lightrag sidecar) with the response
    reflected into the readable session view. Hostname-literal checks only (no
    DNS resolution); pair with network egress policy for defence in depth. A
    refused URL degrades exactly like an unreachable one (caller falls back to
    treating the input as pasted text).
    """
    import ipaddress
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".internal")):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True  # non-IP hostname: allowed (see docstring caveat)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


# Cap on redirect hops we follow manually (each re-validated for SSRF).
_MAX_CV_REDIRECTS = 5


async def _fetch_url_bytes(cv_url: str) -> tuple[bytes, str] | None:
    """读取文件并返回 (bytes, content_type)，失败返回 None。

    手动跟随有限次重定向并逐跳校验目标，避免公网 URL 跳转内网后绕过检查。
    """
    if not _is_fetchable_url(cv_url):
        log.warning("fetch_cv: refusing non-public URL %r", cv_url)
        return None
    try:
        async with httpx.AsyncClient(timeout=_CV_FETCH_TIMEOUT_SEC) as client:
            url = cv_url
            for _ in range(_MAX_CV_REDIRECTS + 1):
                resp = await client.get(url, follow_redirects=False)
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return None
                    nxt = str(resp.url.join(location))
                    if not _is_fetchable_url(nxt):
                        log.warning(
                            "fetch_cv: refusing redirect to non-public URL %r", nxt
                        )
                        return None
                    url = nxt
                    continue
                resp.raise_for_status()
                return resp.content, resp.headers.get("content-type", "")
            log.warning("fetch_cv: too many redirects for %r", cv_url)
            return None
    except Exception as exc:  # noqa: BLE001 - best-effort: fetch failure -> caller falls back
        log.warning("fetch_cv: could not GET %r (%s)", cv_url, exc)
        return None


async def _extract_from_bytes(data: bytes, mime: str, deps: Deps) -> tuple[str, list[str]]:
    """Convert document ``data`` to text: markitdown first, Gemini fallback.

    Returns ``(text, warnings)``. On total failure returns ``("", [warning])`` —
    never the raw bytes/base64, which would feed garbage into ``cv_analysis``.
    """
    text = await asyncio.to_thread(_markitdown_extract, data, mime)
    if text and _is_meaningful(text):
        return text, []

    # Fallback: native multimodal document understanding for scanned/image PDFs.
    settings = deps.settings
    gemini_ready = bool(settings.gemini_api_key) and (
        (settings.llm_provider or "").lower() == "gemini"
    )
    if gemini_ready:
        fallback = await _gemini_extract(data, mime, deps)
        if fallback and _is_meaningful(fallback):
            return fallback, []

    # markitdown gave us *something* but it didn't pass the meaningfulness bar;
    # still prefer it over nothing (downstream validation makes the final call).
    if text:
        return text, []

    return "", [_UNREADABLE_WARNING]


async def extract_cv_text(cv_url: str, deps: Deps) -> tuple[str, list[str]]:
    """返回 (text, warnings)：粘贴文本原样返回，data URL 解码后解析，HTTP(S) 文件读取后解析。

    远程读取失败时保留原 URL 且不追加警告，以兼容离线流程；
    远程内容解析为空时保留原 URL 和解析警告。
    """
    if not cv_url:
        return "", []

    # 1) data: URL of raw file bytes (the no-R2 upload path).
    decoded = _decode_data_url(cv_url)
    if decoded is not None:
        data, mime = decoded
        return await _extract_from_bytes(data, mime, deps)

    # 2) http(s) URL pointing at a document (the R2 / hosted-file path).
    stripped = cv_url.strip()
    if stripped.lower().startswith(("http://", "https://")) and "\n" not in stripped:
        fetched = await _fetch_url_bytes(stripped)
        if fetched is None:
            # Fetch failed: the URL string is still a meaningful pointer. Preserve
            # the legacy behaviour the offline prep test depends on (no warning).
            return cv_url, []
        data, content_type = fetched
        text, warnings = await _extract_from_bytes(data, content_type, deps)
        if text:
            return text, warnings
        # Couldn't parse the fetched bytes: fall back to the URL as the pointer.
        return cv_url, warnings

    # 3) Plain text — the paste path. Return verbatim, no parsing.
    return cv_url, []
