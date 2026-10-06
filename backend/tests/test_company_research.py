"""验证原生联网工具、来源校验及研究结果在面试中的使用，不访问网络。"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.adapters.base import GroundedResearch
from app.core.adapters.mock import build_mock
from app.core.adapters.research import (
    GeminiResearch,
    MiniMaxResearch,
    OpenAIResearch,
    ResearchUnavailable,
    UnavailableResearch,
    get_research,
)
from app.core.config import Settings
from app.dependencies.container import build_deps
from app.schemas.shared_models import Citation, CompanyIntel, InterviewContext
from app.services.live.state import InterviewUserdata, compact_summary
from app.services.prep.nodes import company_research
from app.services.prep.prompts import question_planner_prompts

from .test_prep import _request


def _source():
    return Citation(title="Company careers", url="https://company.example/careers")


def test_minimax_runs_native_search_and_extracts_actual_results(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"content": [
            {"type": "text", "text": "Company builds payment APIs."},
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "title": "Careers",
                 "url": "https://company.example/careers", "content": "Technical interview"},
                {"type": "web_search_result", "url": "javascript:alert(1)"},
            ]},
        ]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(respond),
    ))
    result = asyncio.run(MiniMaxResearch("test-key", "MiniMax-M3", "https://api.minimax.io", 10)
                         .research(system="research", user="Company"))
    assert requests[0].url.path == "/anthropic/v1/messages"
    payload = json.loads(requests[0].content)
    assert payload["tools"] == [{"type": "web_search_20250305", "name": "web_search"}]
    assert requests[0].headers["x-api-key"] == "test-key"
    assert result.sources[0].snippet == "Technical interview"
    assert len(result.sources) == 1


def test_minimax_refuses_unsearched_model_claims(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "content": [{"type": "text", "text": "I searched https://company.example."}],
        })),
    ))
    with pytest.raises(ResearchUnavailable):
        asyncio.run(MiniMaxResearch("test", "MiniMax-M3", "https://api.minimax.io", 10)
                    .research(system="s", user="u"))


@pytest.mark.parametrize("narrative", ["I'll research OpenAI for this candidate.", ""])
def test_minimax_tool_excerpts_reach_summarizer_without_a_final_report(monkeypatch, narrative):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "content": [
                {"type": "text", "text": narrative},
                {"type": "web_search_tool_result", "content": [
                    {"type": "web_search_result", "title": "OpenAI products",
                     "url": "https://openai.com", "content": "OpenAI develops ChatGPT."},
                ]},
            ],
        })),
    ))
    deps = build_deps()
    deps.research = MiniMaxResearch("test", "MiniMax-M3", "https://api.minimax.io", 10)

    class LLM:
        async def complete_json(self, **kwargs):
            assert "OpenAI develops ChatGPT." in kwargs["user"]
            assert "https://openai.com" in kwargs["user"]
            return build_mock(CompanyIntel).model_copy(update={
                "summary": "OpenAI develops ChatGPT.",
            })

    deps.llm = LLM()

    async def exercise():
        req = _request().model_copy(update={"company": "OpenAI"})
        sid = await deps.repo.create_session(req)
        intel = (await company_research({"req": req, "session_id": sid}, deps))["company"]
        view = await deps.repo.get_session_view(sid)
        assert intel.research_status == "complete"
        assert intel.sources[0].snippet == "OpenAI develops ChatGPT."
        assert view.prep_step_statuses["company_research"] == "complete"
        assert not view.prep_warnings

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", [408, 429, 500, 529, "connect", "read_timeout"])
def test_minimax_recovers_from_transient_failures_with_verified_sources(monkeypatch, failure):
    attempts, delays = [], []
    real_client = httpx.AsyncClient

    def respond(request):
        attempts.append(request)
        if len(attempts) < 3:
            if failure == "connect":
                raise httpx.ConnectError("temporary failure", request=request)
            if failure == "read_timeout":
                raise httpx.ReadTimeout("temporary timeout", request=request)
            return httpx.Response(failure, json={"error": "temporary failure"})
        return httpx.Response(200, json={"content": [
            {"type": "text", "text": "Company builds payment APIs."},
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "title": "Company careers",
                 "url": "https://company.example/careers"},
            ]},
        ]})

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(asyncio, "sleep", sleep)
    result = asyncio.run(MiniMaxResearch("test", "MiniMax-M3", "https://api.minimax.io", 10)
                         .research(system="s", user="u"))
    assert result.sources == [_source()]
    assert len(attempts) == 3
    assert delays == [1, 2]
    assert all(request.content == attempts[0].content for request in attempts)


@pytest.mark.parametrize("status, expected_attempts", [(400, 1), (401, 1), (403, 1), (529, 3)])
def test_minimax_does_not_retry_permanent_errors_or_retry_forever(
    monkeypatch, caplog, status, expected_attempts,
):
    attempts = []
    real_client = httpx.AsyncClient

    def respond(request):
        attempts.append(request)
        return httpx.Response(status, json={"error": "private-response-detail"})

    async def sleep(delay):
        pass

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        **kw, transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        asyncio.run(MiniMaxResearch("private-key", "MiniMax-M3", "https://api.minimax.io", 10)
                    .research(system="s", user="private-cv-text"))
    assert caught.value.response.status_code == status
    assert len(attempts) == expected_attempts
    assert "private-key" not in caplog.text
    assert "private-cv-text" not in caplog.text
    assert "private-response-detail" not in caplog.text


def test_minimax_retry_backoff_is_inside_total_timeout_and_closes_client(monkeypatch):
    attempts, clients = [], []
    real_client = httpx.AsyncClient

    def respond(request):
        attempts.append(request)
        return httpx.Response(529)

    def client(**kwargs):
        instance = real_client(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(instance)
        return instance

    monkeypatch.setattr(httpx, "AsyncClient", client)
    # 一秒退避必须被总预算中断，不能额外等待或启动下一次尝试。
    with pytest.raises(TimeoutError):
        asyncio.run(MiniMaxResearch("test", "MiniMax-M3", "https://api.minimax.io", 0.02)
                    .research(system="s", user="u"))
    assert len(attempts) == 1
    assert clients[0].is_closed


def test_openai_requires_search_and_uses_tool_citations(monkeypatch):
    calls = []
    closed = []
    source = SimpleNamespace(model_dump=lambda: _source().model_dump())

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="Company research", output=[
            SimpleNamespace(type="web_search_call", status="completed",
                            action=SimpleNamespace(sources=[source])),
        ])

    async def close():
        closed.append(True)

    monkeypatch.setattr(OpenAIResearch, "_client", lambda _: SimpleNamespace(
        responses=SimpleNamespace(create=create), close=close,
    ))
    result = asyncio.run(OpenAIResearch("test", "model").research(system="s", user="u"))
    assert calls[0]["tools"] == [{"type": "web_search"}]
    assert calls[0]["tool_choice"] == "required"
    assert result.sources == [_source()]
    assert closed


def test_gemini_enables_grounding_and_preserves_search_suggestions(monkeypatch):
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="Company research", candidates=[SimpleNamespace(
            grounding_metadata=SimpleNamespace(
                web_search_queries=["company careers"],
                grounding_chunks=[SimpleNamespace(web=SimpleNamespace(
                    title="Company careers", uri="https://company.example/careers",
                ))],
                search_entry_point=SimpleNamespace(rendered_content="<div>Search</div>"),
            ),
        )])

    async def close():
        pass

    monkeypatch.setattr(GeminiResearch, "_client", lambda _: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate), aclose=close),
        close=lambda: None,
    ))
    result = asyncio.run(GeminiResearch("test", "model").research(system="s", user="u"))
    assert calls[0]["config"]["tools"] == [{"google_search": {}}]
    assert result.search_suggestions == "<div>Search</div>"
    assert result.sources == [_source()]


@pytest.mark.parametrize("provider", ["mock", "ollama", "unknown", "minimax"])
def test_no_keys_or_offline_provider_never_fabricates_research(provider):
    settings = Settings(_env_file=None, llm_provider=provider)
    assert isinstance(get_research(settings), UnavailableResearch)


def test_company_research_supplies_verified_sources_to_plan_and_live_context(monkeypatch):
    deps = build_deps()
    calls = []

    class Research:
        async def research(self, **kwargs):
            calls.append(kwargs)
            return GroundedResearch(text="Company uses Go and interviews on design.",
                                    sources=[_source()])

    class LLM:
        async def complete_json(self, **kwargs):
            assert "Company uses Go" in kwargs["user"]
            # 模型捏造的来源必须被真正的工具来源覆盖。
            return CompanyIntel(name="Wrong", summary="Payment APIs", industry="Fintech",
                                tech_stack=["Go"], values=["Ownership"],
                                interview_process=["System design"],
                                recent_news=[f"News {i}" for i in range(10)],
                                sources=[Citation(title="Invented", url="https://fake.example")])

    monkeypatch.setattr(deps, "research", Research())
    monkeypatch.setattr(deps, "llm", LLM())
    result = asyncio.run(company_research({"req": _request(primary="zh")}, deps))
    company = result["company"]
    assert company.name == "ExampleCorp"
    assert company.research_status == "complete"
    assert company.sources == [_source()]
    assert company.recent_news == ["News 0", "News 1", "News 2"]
    assert "Chinese" in calls[0]["user"]
    assert "Senior Backend Engineer" in calls[0]["user"]
    ctx = build_mock(InterviewContext).model_copy(update={"company": company})
    _, planner = question_planner_prompts(
        ctx.candidate, ctx.job, company, ctx.gap, ctx.plan.language_mode,
    )
    assert "System design" in planner
    summary = compact_summary(InterviewUserdata(session_id=ctx.session_id, ctx=ctx))
    assert "Payment APIs" in summary and "Go" in summary and "Ownership" in summary
    assert "System design" in summary


def test_failed_research_marks_progress_warns_and_never_calls_summarizer(monkeypatch):
    deps = build_deps()

    class Research:
        async def research(self, **kwargs):
            raise TimeoutError()

    class LLM:
        async def complete_json(self, **kwargs):
            pytest.fail("Must not summarize without search evidence")

    monkeypatch.setattr(deps, "research", Research())
    monkeypatch.setattr(deps, "llm", LLM())

    async def exercise():
        req = _request()
        sid = await deps.repo.create_session(req)
        result = await company_research({"req": req, "session_id": sid}, deps)
        view = await deps.repo.get_session_view(sid)
        return result["company"], view

    company, view = asyncio.run(exercise())
    assert company.summary == "" and company.sources == []
    assert company.research_status == "unavailable"
    assert company.research_error == "timeout"
    assert view.prep_step_statuses["company_research"] == "unavailable"
    assert "company_research" in view.progress
    assert any("web research is unavailable" in w for w in view.prep_warnings)


def test_invalid_company_skips_research(monkeypatch):
    deps = build_deps()

    class Research:
        async def research(self, **kwargs):
            pytest.fail("Invalid company must not trigger web research")

    monkeypatch.setattr(deps, "research", Research())
    company = asyncio.run(company_research({"req": _request(), "company_ok": False}, deps))
    assert company["company"].summary == ""
    assert company["company"].research_error == "invalid_company"


def test_search_sources_without_usable_company_facts_are_not_success(monkeypatch):
    deps = build_deps()

    class Research:
        async def research(self, **kwargs):
            return GroundedResearch(text="No confirmed company facts.", sources=[_source()])

    class LLM:
        async def complete_json(self, **kwargs):
            return build_mock(CompanyIntel).model_copy(update={"summary": " "})

    monkeypatch.setattr(deps, "research", Research())
    monkeypatch.setattr(deps, "llm", LLM())
    company = asyncio.run(company_research({"req": _request()}, deps))["company"]
    assert company.research_status == "unavailable"
    assert company.research_error == "no_sources"


def test_research_only_completes_after_search_and_structuring(monkeypatch):
    deps = build_deps()

    async def exercise():
        req = _request()
        sid = await deps.repo.create_session(req)
        searching, searched, structuring, structured = (asyncio.Event() for _ in range(4))

        class Research:
            async def research(self, **kwargs):
                searching.set()
                await searched.wait()
                return GroundedResearch(text="Payment APIs", sources=[_source()])

        class LLM:
            async def complete_json(self, **kwargs):
                structuring.set()
                await structured.wait()
                return build_mock(CompanyIntel)

        monkeypatch.setattr(deps, "research", Research())
        monkeypatch.setattr(deps, "llm", LLM())
        task = asyncio.create_task(company_research({"req": req, "session_id": sid}, deps))
        await searching.wait()
        view = await deps.repo.get_session_view(sid)
        assert view.prep_step_statuses["company_research"] == "running"
        assert "company_research" not in view.progress
        searched.set()
        await structuring.wait()
        view = await deps.repo.get_session_view(sid)
        assert view.prep_step_statuses["company_research"] == "running"
        assert "company_research" not in view.progress
        structured.set()
        await task
        view = await deps.repo.get_session_view(sid)
        assert view.prep_step_statuses["company_research"] == "complete"
        assert "company_research" in view.progress

    asyncio.run(exercise())


@pytest.mark.parametrize("reason", ["not_configured", "no_sources", "request_failed"])
def test_unavailable_reason_reaches_company_card(monkeypatch, reason):
    deps = build_deps()

    class Research:
        async def research(self, **kwargs):
            raise ResearchUnavailable("Unavailable", reason)

    monkeypatch.setattr(deps, "research", Research())
    company = asyncio.run(company_research({"req": _request()}, deps))["company"]
    assert company.research_error == reason
    assert company.research_status == "unavailable"
    assert not company.sources
