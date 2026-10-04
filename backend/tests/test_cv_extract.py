"""离线验证粘贴文本和 data URL 的文档提取，本地转换真实执行，多模态调用用替身。"""

from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from app.core.config import Settings
from app.dependencies.container import build_deps
from app.schemas.shared_models import LanguageMode, PrepRequest
from app.services.prep import cv_extract
from app.services.prep.cv_extract import extract_cv_text
from app.services.prep.nodes import fetch_cv

_REAL_CV = (
    "Jane Doe — Senior Backend Engineer. 8 years of Python, Kafka, and "
    "distributed payment systems. Led three teams and owned service reliability."
)


def _data_url(text: str, mime: str = "text/plain") -> str:
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"data:{mime};base64,{b64}"


def test_plain_text_passthrough_unchanged() -> None:
    """粘贴文本必须原样返回。"""
    deps = build_deps()
    text, warnings = asyncio.run(extract_cv_text(_REAL_CV, deps))
    assert text == _REAL_CV
    assert warnings == []


def test_data_url_text_is_decoded_and_converted() -> None:
    """base64 文档载荷必须先解码再转换为正文。"""
    deps = build_deps()
    url = _data_url(_REAL_CV, mime="text/plain")
    text, warnings = asyncio.run(extract_cv_text(url, deps))
    assert "Jane Doe" in text
    assert "distributed payment systems" in text
    assert warnings == []


def test_markitdown_handles_markdown_data_url() -> None:
    """Markdown 文档 data URL 应交给本地转换器处理。"""
    deps = build_deps()
    md = f"# Résumé\n\n## Summary\n\n{_REAL_CV}\n\n- Python\n- Kafka\n"
    url = _data_url(md, mime="text/markdown")
    text, warnings = asyncio.run(extract_cv_text(url, deps))
    assert "Jane Doe" in text
    assert warnings == []


def test_gemini_fallback_used_when_markitdown_empty(monkeypatch) -> None:
    """本地转换为空时才调用配置完整的 Gemini 提取兜底。"""
    # 多模态兜底检查提供方及密钥，与 deps.llm 的模拟适配器无关。
    deps = build_deps(Settings(llm_provider="gemini", gemini_api_key="test-key"))

    calls = {"markitdown": 0, "gemini": 0}

    def _empty_markitdown(data: bytes, mime: str) -> str:
        calls["markitdown"] += 1
        return ""

    async def _fake_gemini(data: bytes, mime: str, d) -> str:
        calls["gemini"] += 1
        return _REAL_CV

    monkeypatch.setattr(cv_extract, "_markitdown_extract", _empty_markitdown)
    monkeypatch.setattr(cv_extract, "_gemini_extract", _fake_gemini)

    url = _data_url("ignored — markitdown is stubbed to empty", mime="application/pdf")
    text, warnings = asyncio.run(extract_cv_text(url, deps))

    assert text == _REAL_CV
    assert warnings == []
    assert calls["markitdown"] == 1
    assert calls["gemini"] == 1


def test_gemini_fallback_not_called_when_markitdown_succeeds(monkeypatch) -> None:
    """本地提取成功时不得再调用多模态模型。"""
    deps = build_deps(Settings(llm_provider="gemini", gemini_api_key="test-key"))

    calls = {"gemini": 0}

    async def _fake_gemini(data: bytes, mime: str, d) -> str:
        calls["gemini"] += 1
        return "SHOULD NOT BE USED"

    monkeypatch.setattr(cv_extract, "_gemini_extract", _fake_gemini)

    url = _data_url(_REAL_CV, mime="text/plain")
    text, warnings = asyncio.run(extract_cv_text(url, deps))

    assert "Jane Doe" in text
    assert calls["gemini"] == 0
    assert warnings == []


def test_unreadable_document_warns_and_returns_empty(monkeypatch) -> None:
    """转换全失败时返回空正文和警告，不能把二进制载荷当作简历。"""
    deps = build_deps()

    monkeypatch.setattr(cv_extract, "_markitdown_extract", lambda data, mime: "")

    url = _data_url("x", mime="application/pdf")
    text, warnings = asyncio.run(extract_cv_text(url, deps))

    assert text == ""
    assert len(warnings) == 1
    assert "Couldn't read" in warnings[0]


def _prep_request(cv_url: str) -> PrepRequest:
    return PrepRequest(
        cv_url=cv_url,
        jd_text="We are hiring a backend engineer to build payment systems.",
        company="Acme",
        language_mode=LanguageMode(primary="en", mixed=False),
    )


def test_fetch_cv_node_is_idempotent_even_when_text_empty(monkeypatch) -> None:
    """cv_text 键存在即表示已解析，空正文也不能触发重复提取或模型费用。"""
    called = {"extract": 0}

    async def _boom(cv_url: str, d):  # pragma: no cover - 此路径不得执行
        called["extract"] += 1
        return "should not be called", []

    monkeypatch.setattr("app.services.prep.nodes.extract_cv_text", _boom)

    deps = build_deps()
    state = {"req": _prep_request("data:text/plain;base64,xxxx"), "cv_text": ""}
    result = asyncio.run(fetch_cv(state, deps))

    assert result == {}
    assert called["extract"] == 0


@pytest.mark.parametrize("url", ["http://localhost./cv", "http://a.localhost./cv", "https://user:pass@example.com/cv"])
def test_unsafe_document_urls_are_rejected(url):
    assert not cv_extract._is_fetchable_url(url)


def test_malformed_data_url_never_reaches_candidate_analysis():
    text, warnings = asyncio.run(extract_cv_text("data:application/pdf;base64,%%%", build_deps()))
    assert text == ""
    assert warnings


@pytest.mark.parametrize("declared_size", [True, False])
def test_remote_cv_size_limit_handles_headers_and_streams(monkeypatch, declared_size):
    monkeypatch.setattr(cv_extract, "_MAX_DOCUMENT_BYTES", 10)
    client_type = httpx.AsyncClient
    headers = {"content-length": "1000"} if declared_size else {}

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"a" * 20

    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers=headers, stream=Stream()))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    assert asyncio.run(cv_extract._fetch_url_bytes("https://example.com/cv")) is None


def test_cv_redirect_to_private_host_is_not_followed(monkeypatch):
    seen = []
    client_type = httpx.AsyncClient

    def respond(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/cv"})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    assert asyncio.run(cv_extract._fetch_url_bytes("https://example.com/cv")) is None
    assert seen == ["https://example.com/cv"]


def test_extracted_text_budget_adds_a_warning(monkeypatch):
    monkeypatch.setattr(cv_extract, "_MAX_EXTRACTED_CHARS", 30)
    text, warnings = asyncio.run(extract_cv_text(_data_url(_REAL_CV), build_deps()))
    assert len(text) == 30
    assert "truncated" in warnings[0]
