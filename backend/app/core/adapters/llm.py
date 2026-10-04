"""LLM adapter factory + real adapters (lazy-imported SDKs).

``get_llm(settings)`` returns the deterministic :class:`MockLLM` unless an LLM
provider is selected *and* its API key is present; otherwise it logs a warning
and falls back to the mock. Real adapters import their SDK inside methods so the
module imports cleanly with no SDK installed.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ..logging import get_logger
from .base import LLMAdapter
from .mock import MockLLM

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger(__name__)

# Per-call ceiling so a stalled provider call can never hang a pipeline forever
# (the prep graph's per-node try/except only fires once the call RETURNS).
_DEFAULT_TIMEOUT_SEC = 90.0


def _tool_schema(schema: type) -> dict[str, Any]:
    """Inline local refs for compatible providers that mishandle nested $defs."""
    root = schema.model_json_schema()

    def expand(value: Any, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(value, list):
            return [expand(v, seen) for v in value]
        if not isinstance(value, dict):
            return value
        ref = value.get("$ref")
        if ref and ref.startswith("#/$defs/"):
            if ref in seen:
                raise ValueError("Recursive schemas are not supported by the MiniMax output tool")
            target = root["$defs"][ref.rsplit("/", 1)[-1]]
            return expand({**target, **{k: v for k, v in value.items() if k != "$ref"}}, seen + (ref,))
        return {
            k: expand(v, seen) for k, v in value.items()
            if k != "$defs" and not (k == "title" and isinstance(v, str))
        }

    result = expand(root)
    if schema.__name__ == "QuestionPlan":
        from ...schemas.shared_models import LANGUAGES

        # LocalizedText's AfterValidator is absent from its JSON Schema. Encode
        # that contract in the output tool as well as validating it afterwards.
        result["properties"]["questions"]["items"]["properties"]["text"] = {
            "type": "object",
            "properties": {lang: {"type": "string"} for lang in LANGUAGES},
            "required": ["en"],
            "additionalProperties": False,
        }
    return result


def _normalize_arrays(value: Any, contract: dict[str, Any]) -> Any:
    """Losslessly unwrap MiniMax's occasional {item: [...]} array envelopes.

    Redundant nesting in string lists is flattened in source order. A string
    where a string-list is required is a one-item list. No missing
    fields are filled and no source text is rewritten; validation still follows.
    """
    if contract.get("type") == "array":
        items = contract.get("items", {})
        if isinstance(value, dict) and len(value) == 1 and next(iter(value)) in {"item", "items"}:
            value = next(iter(value.values()))
        if (
            isinstance(value, str) and items.get("type") == "string"
            or isinstance(value, dict) and items.get("type") == "object"
        ):
            value = [value]
        if isinstance(value, list):
            if items.get("type") == "string":
                flattened = []
                for v in value:
                    normalized = (
                        _normalize_arrays(v, contract) if isinstance(v, (list, dict)) else v
                    )
                    if isinstance(normalized, list):
                        flattened.extend(normalized)
                    else:
                        # Unknown objects/numbers must still fail validation.
                        flattened.append(normalized)
                return flattened
            return [_normalize_arrays(v, items) for v in value]
    elif isinstance(value, dict) and contract.get("type") == "object":
        properties = contract.get("properties", {})
        return {k: _normalize_arrays(v, properties.get(k, {})) for k, v in value.items()}
    return value


def _schema_prompt(system: str, schema: type) -> str:
    """Append the JSON Schema to the system prompt (provider-agnostic).

    Both Gemini's ``response_schema`` and OpenAI's strict structured outputs
    reject free-form maps like our ``LocalizedText = dict[str, str]``
    (additionalProperties), so the reliable cross-provider pattern is JSON mode
    + the schema in the prompt + Pydantic validation of the result.
    """
    schema_json = json.dumps(schema.model_json_schema())
    return (
        f"{system}\n\nGenerate the actual data requested by the user as a single JSON object. "
        f"Its top-level fields are: {', '.join(schema.model_fields)}. "
        "The JSON Schema below describes the output contract; do NOT return or copy "
        "the schema itself ($defs, properties, required, type, title). "
        f"No markdown or commentary.\nOUTPUT CONTRACT:\n{schema_json}\n\n"
        "Return the populated data object, not the contract."
    )


def _loads_json(text: str, schema: type | None = None, *, normalize_arrays: bool = False) -> Any:
    """Parse JSON from an LLM response, tolerating ```json fences, stray prose, and
    *trailing* "Extra data".

    With a schema, select the first complete top-level value that validates.
    An echoed contract must not hide a valid answer after it, and nested objects
    in an invalid/truncated response must never be mistaken for the answer.

    The keystone failure this fixes: the question planner has the largest schema,
    so its real Gemini response is the biggest — and a complete JSON object was
    sometimes FOLLOWED by extra content (a second object / trailing commentary).
    Plain ``json.loads`` raises ``Extra data`` on that, and the old greedy
    ``\\{.*\\}`` fallback spanned to the LAST brace (swallowing the trailing junk
    into invalid JSON), so every plan silently fell back to the generic mock —
    an interview that asks one question literally titled "mock". ``raw_decode``
    returns the FIRST complete JSON value and ignores anything after it.
    """
    import re

    def validate(obj: Any) -> Any:
        if schema is None:
            return obj
        if normalize_arrays:
            obj = _normalize_arrays(obj, _tool_schema(schema))
        return schema.model_validate(obj)

    t = (text or "").strip()
    # Strip reasoning blocks BEFORE looking for JSON. Local reasoning models
    # (Qwen3 via Ollama) routinely return "<think>…</think>" inline in content,
    # and the tolerant scan below takes the FIRST '{' it sees — so a brace
    # anywhere in the model's scratchpad would be decoded instead of the answer.
    # Cloud models don't emit these tags, so this is a no-op for them.
    t = re.sub(r"<(think|thinking)>.*?</\1>", "", t, flags=re.DOTALL | re.IGNORECASE).strip()
    # An unterminated block means the reply was cut off mid-thought; everything
    # after the opening tag is scratchpad, never the answer.
    t = re.sub(r"<(think|thinking)>.*\Z", "", t, flags=re.DOTALL | re.IGNORECASE).strip()
    # Strip a wrapping ```json ... ``` / ``` ... ``` markdown fence, if present.
    if t.startswith("```"):
        t = re.sub(r"^```[^\n]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    # Fast path: a single clean JSON value.
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        pass
    else:
        return validate(obj)
    # Tolerant path: decode the first complete JSON value starting at the first
    # '{' or '[', ignoring any trailing data (raw_decode is "Extra data"-safe).
    decoder = json.JSONDecoder()
    i = 0
    validation_error = None
    while i < len(t):
        ch = t[i]
        if ch in "{[":
            try:
                obj, _end = decoder.raw_decode(t, i)
            except json.JSONDecodeError:
                if schema:
                    # Never accept a nested object from a truncated outer response.
                    raise
                i += 1
                continue
            if schema is None:
                return obj
            try:
                return validate(obj)
            except ValidationError as exc:
                validation_error = exc
                # Skip this entire value (e.g. an echoed schema), including its
                # nested $defs, before looking for the actual answer.
                i = _end
                continue
        i += 1
    if validation_error is not None:
        raise validation_error
    raise json.JSONDecodeError("no JSON value found in LLM response", t, 0)


class GeminiLLM:
    """Google Gemini via ``google-genai`` (lazy import)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        # No default model: ids retire fast, so the current id lives in ONE
        # place (Settings.gemini_model) and must be passed in explicitly.
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec

    def _client(self) -> Any:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depends on optional SDK
            raise RuntimeError(
                "google-genai is not installed; install the 'gemini' extra."
            ) from exc
        return genai.Client(api_key=self._api_key)

    async def complete_text(self, *, system: str, user: str) -> str:
        client = self._client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config={"system_instruction": system},
            ),
            timeout=self._timeout,
        )
        return resp.text or ""

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        # JSON mode + schema-in-prompt (see _schema_prompt for why not
        # ``response_schema``).
        client = self._client()
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self._model,
                contents=user,
                config={
                    "system_instruction": _schema_prompt(system, schema),
                    "response_mime_type": "application/json",
                },
            ),
            timeout=self._timeout,
        )
        return _loads_json(resp.text or "{}", schema)


class OpenAILLM:
    """OpenAI — and any OpenAI-compatible server — via the ``openai`` SDK.

    ``base_url`` is what makes the local path possible: pointed at Ollama's
    ``/v1`` it drives the whole prep/post pipeline with no cloud key. See
    :class:`OllamaLLM`.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
        base_url: str | None = None,
    ) -> None:
        # No default model — see GeminiLLM.__init__; Settings.openai_model is
        # the single source of truth.
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec
        self._base_url = base_url

    def _client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional SDK
            raise RuntimeError(
                "openai is not installed; install the 'openai' extra."
            ) from exc
        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    async def complete_text(self, *, system: str, user: str) -> str:
        client = self._client()
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ),
            timeout=self._timeout,
        )
        return resp.choices[0].message.content or ""

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        # JSON mode + schema-in-prompt, NOT strict structured outputs: OpenAI's
        # strict mode rejects free-form maps (additionalProperties) like our
        # ``LocalizedText = dict[str, str]``, which would silently break the
        # question planner (every plan falling back to mock). Same pattern as
        # the Gemini adapter; Pydantic validates the result either way.
        client = self._client()
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _schema_prompt(system, schema)},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            ),
            timeout=self._timeout,
        )
        return _loads_json(resp.choices[0].message.content or "{}", schema)


class MiniMaxLLM(OpenAILLM):
    """MiniMax through its OpenAI-compatible Chat Completions endpoint.

    MiniMax's documented Chat Completions API doesn't list OpenAI's
    ``response_format`` JSON mode, so structured pipeline responses rely on
    a function's parameter schema and Pydantic validation instead. The function
    is only an output envelope; no tool is executed.
    """

    _RETRY_NUDGE = (
        "Your previous reply could not be parsed as the requested JSON. Call "
        "submit_result with the complete data object — no schema definitions, "
        "explanation, markdown fence, or <think> block."
    )

    async def complete_text(self, *, system: str, user: str) -> str:
        """Plain prose without a tool/schema contract or inline reasoning."""
        extra_body: dict[str, Any] = {"reasoning_split": True}
        if self._model.lower() == "minimax-m3":
            extra_body["thinking"] = {"type": "disabled"}
        client = self._client().with_options(max_retries=0, timeout=self._timeout)
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    extra_body=extra_body,
                ),
                timeout=self._timeout,
            )
            if not resp.choices:
                raise ValueError("empty_choices")
            if getattr(resp.choices[0], "finish_reason", None) == "length":
                raise ValueError("output_truncated")
            return resp.choices[0].message.content or ""
        finally:
            await client.close()

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        prompt = (
            f"{system}\n\nReturn the populated result by calling submit_result. "
            "Its parameter schema is an output contract, not the data to return. "
            f"Populate these top-level fields: {', '.join(schema.model_fields)}."
        )
        output_tool = {
            "type": "function",
            "function": {
                "name": "submit_result",
                "description": "Submit the complete structured result for the user's request.",
                "parameters": _tool_schema(schema),
            },
        }
        extra_body: dict[str, Any] = {"reasoning_split": True}
        if self._model.lower() == "minimax-m3" and schema.__name__ in {
            "CandidateProfile", "JobSpec", "CompanyIntel", "GapAnalysis", "QuestionPlan",
        }:
            # M3 defaults to thinking, which can exhaust the 90s call ceiling
            # before emitting data. M3.1/M2 cannot disable thinking.
            extra_body["thinking"] = {"type": "disabled"}
        # Own retries here; nested SDK retries make latency unpredictable.
        client = self._client().with_options(max_retries=0, timeout=self._timeout)
        try:
            for attempt in range(2):
                try:
                    resp = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=self._model,
                            messages=[
                                {"role": "system", "content": prompt},
                                {"role": "user", "content": user},
                            ],
                            temperature=0.2,
                            tools=[output_tool],
                            tool_choice={"type": "function", "function": {"name": "submit_result"}},
                            extra_body=extra_body,
                        ),
                        timeout=self._timeout,
                    )
                    if not resp.choices:
                        raise ValueError("empty_choices")
                    choice = resp.choices[0]
                    if getattr(choice, "finish_reason", None) == "length":
                        raise ValueError("output_truncated")
                    tool_calls = getattr(choice.message, "tool_calls", None) or []
                    if tool_calls:
                        if len(tool_calls) != 1 or tool_calls[0].function.name != "submit_result":
                            raise ValueError("unexpected_output_tool")
                        return _loads_json(
                            tool_calls[0].function.arguments, schema, normalize_arrays=True,
                        )
                    # Compatible gateways may emit content instead of a tool
                    # envelope. It still has to pass the same validation.
                    return _loads_json(choice.message.content or "", schema, normalize_arrays=True)
                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    retryable = (
                        isinstance(exc, (ValueError, TimeoutError))
                        or type(exc).__name__ in {"APITimeoutError", "APIConnectionError"}
                        or status in {408, 409, 429}
                        or (isinstance(status, int) and status >= 500)
                    )
                    if attempt or not retryable:
                        raise
                    # Log only error types/field paths, never CV/JD/output data.
                    detail = type(exc).__name__
                    if isinstance(exc, ValidationError):
                        fields = [
                            ".".join(str(p) for p in e["loc"]) + f": {e['msg']}"
                            for e in exc.errors(include_input=False, include_context=False)[:8]
                        ]
                        detail += f" at {'; '.join(fields)}"
                    elif isinstance(exc, json.JSONDecodeError):
                        detail += f": {exc.msg} at line {exc.lineno}, column {exc.colno}"
                    log.warning(
                        "MiniMaxLLM: %s schema=%s model=%s; retrying once",
                        detail, schema.__name__, self._model,
                    )
                    prompt = (
                        f"{prompt}\n\n{self._RETRY_NUDGE} "
                        f"The previous failure was {detail[:1500]}. Generate a complete data "
                        "object with the required fields, not a JSON Schema."
                    )
                    if status == 429 or (isinstance(status, int) and status >= 500):
                        await asyncio.sleep(1)
        finally:
            await client.close()
        raise RuntimeError("MiniMaxLLM: JSON generation failed")


class OllamaLLM(OpenAILLM):
    """A local Ollama server through its OpenAI-compatible ``/v1`` endpoint.

    Ollama needs no credential, so a non-empty placeholder key is passed (the
    SDK requires *something*). Behaviourally this differs from the cloud path in
    one way that matters: **it retries once when the response doesn't parse.**

    Why only here. Small local models are markedly worse at emitting strict JSON
    than Gemini/GPT, and this pipeline's largest schema (``QuestionPlan``) is
    also its keystone — when it fails, ``prep.nodes.question_planner`` silently
    swaps in the generic mock plan and the candidate sits through an interview
    whose questions are titled "mock". That exact failure has shipped before.
    One cheap retry with a blunter instruction converts most near-misses
    (a stray preamble, a truncated trailing brace) into a usable plan; the cloud
    adapters stay single-shot so their latency and cost are unchanged.
    """

    _RETRY_NUDGE = (
        "Your previous reply could not be parsed as JSON. Reply with the JSON "
        "value ONLY — no explanation, no markdown fence, no <think> block."
    )

    async def complete_json(self, *, system: str, user: str, schema: type) -> Any:
        try:
            return await super().complete_json(system=system, user=user, schema=schema)
        except Exception as exc:  # noqa: BLE001 - any parse/validation miss earns one retry
            log.warning("OllamaLLM: unparseable JSON (%s); retrying once.", exc)
            return await super().complete_json(
                system=f"{system}\n\n{self._RETRY_NUDGE}", user=user, schema=schema
            )


def get_llm(settings: Settings) -> LLMAdapter:
    """Choose an LLM adapter from settings, falling back to the mock."""
    provider = (settings.llm_provider or "mock").lower()
    if provider == "mock":
        return MockLLM()
    timeout = getattr(settings, "llm_call_timeout_sec", _DEFAULT_TIMEOUT_SEC)
    if provider == "gemini":
        if settings.gemini_api_key:
            return GeminiLLM(settings.gemini_api_key, settings.gemini_model, timeout)
        log.warning("llm_provider=gemini but gemini_api_key is missing; using MockLLM.")
        return MockLLM()
    if provider == "openai":
        if settings.openai_api_key:
            return OpenAILLM(settings.openai_api_key, settings.openai_model, timeout)
        log.warning("llm_provider=openai but openai_api_key is missing; using MockLLM.")
        return MockLLM()
    if provider == "minimax":
        if settings.minimax_api_key:
            return MiniMaxLLM(
                settings.minimax_api_key,
                settings.minimax_model,
                timeout,
                base_url=f"{settings.minimax_base_url.rstrip('/')}/v1",
            )
        log.warning("llm_provider=minimax but minimax_api_key is missing; using MockLLM.")
        return MockLLM()
    if provider in {"ollama", "vllm", "llamacpp", "lmstudio", "local"}:
        # Local: a base URL takes the place of an API key. Everything else in
        # the factory contract is unchanged — missing config still degrades to
        # the mock rather than failing the pipeline.
        if settings.ollama_base_url:
            return OllamaLLM(
                settings.local_api_key,
                settings.ollama_model,
                timeout,
                base_url=settings.ollama_base_url,
            )
        log.warning("llm_provider=%s but ollama_base_url is missing; using MockLLM.", provider)
        return MockLLM()
    log.warning("Unknown llm_provider=%r; using MockLLM.", provider)
    return MockLLM()
