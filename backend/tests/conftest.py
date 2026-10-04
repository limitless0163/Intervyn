"""Pytest configuration: pin the offline suite to the deterministic mock stack.

Every test module here is documented as offline/MockLLM (no API keys, no network)
and several assert run-to-run determinism (e.g. ``test_run_score_is_stable_on_rerun``).
The repo ships a real ``backend/.env`` with live keys and ``LLM_PROVIDER=gemini``
for the live worker; ``pydantic-settings`` would load that and make ``build_deps()``
return the real, non-deterministic Gemini adapter — breaking the determinism tests
and turning a 4-second suite into a multi-minute one that hammers the live key.

We force every provider to ``mock`` via ``os.environ`` BEFORE any test imports
``get_settings()`` (whose result is ``lru_cache``d). ``os.environ`` takes precedence
over ``.env`` in pydantic-settings, so this restores the documented offline contract
regardless of what ``.env`` contains. We likewise BLANK the Supabase creds so
``get_repository()`` falls back to the in-memory repo: a real ``.env`` now ships a
Supabase URL + service-role key, and without this the suite would select
``SupabaseRepository`` and fail on the optional ``supabase`` SDK (not installed in
the test venv). Set ``INTERVYN_TEST_USE_ENV=1`` to opt out (e.g. a deliberate
live integration run).
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("INTERVYN_TEST_USE_ENV") != "1":
    for _var in (
        "LLM_PROVIDER",
        "STT_PROVIDER",
        "TTS_PROVIDER",
        "SEARCH_PROVIDER",
        "EMBEDDINGS_PROVIDER",
    ):
        os.environ[_var] = "mock"
    # Empty string overrides ``.env`` and is falsy, so the
    # ``settings.supabase_url and settings.supabase_service_role_key`` guard in
    # ``get_repository()`` is False → deterministic in-memory ``MemoryRepository``.
    # LIGHTRAG_URL is also blanked so local sidecars cannot replace MockKnowledge.
    for _var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LIGHTRAG_URL"):
        os.environ[_var] = ""
    # Tracing writes JSONL files per run — keep the offline suite hermetic.
    # Tests for tracing itself (test_tracing.py) opt back in per-test via
    # ``tracing.init_tracing(enabled=True, trace_dir=tmp_path)``.
    os.environ["TRACE_ENABLED"] = "0"


@pytest.fixture(autouse=True)
def offline_http(monkeypatch):
    """Real HTTP fails immediately; MockTransport and ASGITransport still work.

    Example CV URLs must exercise the unreachable-host fallback deterministically,
    rather than depending on DNS, remote content, or a five-second fetch timeout.
    HTTP integration tests supply their own transport with explicit responses.
    """
    if os.environ.get("INTERVYN_TEST_USE_ENV") == "1":
        return
    # The independent naive-RAG sidecar has no httpx dependency.
    try:
        import httpx
    except ImportError:
        return

    def reject_http(self, request):
        raise httpx.ConnectError("Network disabled in offline tests", request=request)

    async def reject_async_http(self, request):
        raise httpx.ConnectError("Network disabled in offline tests", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_http)
