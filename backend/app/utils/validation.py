"""通过确定性启发式提前识别空白、重复或随机输入，避免无效模型调用。

仅简历和职位同时无效时拒绝准备；单项无效或公司名无效时返回警告。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..schemas.shared_models import PrepRequest

__all__ = ["assess_text", "validate_prep_inputs"]

_MIN_LEN_CV = 30
_MIN_LEN_JD = 30
_MIN_LEN_COMPANY = 2

# 使用 Unicode 字母占比，避免把中文等非拉丁文字误判为符号。
_MIN_ALPHA_RATIO = 0.45

# 短重复模式覆盖过高时视为无效输入。
_REPETITION_THRESHOLD = 0.70

_VOWELS = set("aeiouyAEIOUY")
_WORD_RUN_RE = re.compile(r"[A-Za-z]{3,}")
_TOKEN_RE = re.compile(r"[A-Za-z]+")

_KIND_LABEL = {"cv": "CV", "jd": "job description", "company": "company name"}


def _friendly(kind: str, reason: str) -> str:
    label = _KIND_LABEL.get(kind, kind)
    return f"The {label} {reason}"


def _looks_like_url(text: str) -> bool:
    """识别单个 HTTP(S) 文档地址或 data URL，避免将文档引用当作随机文字拒绝。"""
    stripped = text.strip()
    # data URL 是文档载荷，不按正文空白或单词结构检查。
    if stripped.startswith("data:"):
        return True
    if " " in stripped or "\n" in stripped:
        return False
    parsed = urlparse(stripped)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _dominant_pattern_ratio(text: str) -> float:
    """计算去空白文本中单字符或二、三字符周期的最大覆盖比例，范围为 0 至 1。"""
    compact = re.sub(r"\s+", "", text)
    n = len(compact)
    if n == 0:
        return 1.0

    most_common_char = Counter(compact).most_common(1)[0][1]
    best = most_common_char / n

    # 至少出现两个完整周期才计重复，避免 IBM 等短公司名被自身模式误判。

    if n >= 4:
        for offset in (0, 1):
            unit = compact[offset : offset + 2]
            if len(unit) < 2:
                continue
            tiled = (unit * (n // 2 + 1))[: n - offset]
            matches = sum(1 for a, b in zip(compact[offset:], tiled) if a == b)
            best = max(best, matches / n)

    if n >= 6:
        unit = compact[:3]
        tiled = (unit * (n // 3 + 1))[:n]
        matches = sum(1 for a, b in zip(compact, tiled) if a == b)
        best = max(best, matches / n)

    return best


def assess_text(text: str, *, kind: str, min_len: int) -> tuple[bool, str | None]:
    """返回 (is_meaningful, reason)；无效时提供用户可读原因，有效时原因为 None。"""
    if text is None:
        return False, _friendly(kind, "looks empty — please paste the real content.")

    stripped = text.strip()

    if not stripped:
        return False, _friendly(kind, "looks empty — please paste the real content.")

    # 简历字段允许文档引用，实际内容由提取步骤校验。
    if kind == "cv" and _looks_like_url(text):
        return True, None

    if len(stripped) < min_len:
        return False, _friendly(
            kind, "is too short to be meaningful — please paste the full content."
        )

    # 使用 Unicode 字母数字判定，保留非拉丁文字内容。
    alnum = [c for c in stripped if c.isalnum()]
    if not alnum:
        return False, _friendly(
            kind, "looks empty or like random symbols — please paste the real content."
        )

    # 字母判定支持 Unicode；数字和符号过多时视为非正文。
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) / len(stripped) < _MIN_ALPHA_RATIO:
        return False, _friendly(
            kind,
            "looks empty or like random characters — please paste the real content.",
        )

    # 单词及元音规则只用于 ASCII 占主导的文本，避免误拒绝中文等非拉丁语言。
    ascii_letters = sum(1 for c in letters if c.isascii())
    if ascii_letters / len(letters) >= 0.5:
        if not _WORD_RUN_RE.search(stripped):
            return False, _friendly(
                kind,
                "looks empty or like random characters — please paste the real content.",
            )

        # 元音规则是拉丁文本的启发式，不是通用语言判定。
        tokens = _TOKEN_RE.findall(stripped)
        if tokens and not any(any(ch in _VOWELS for ch in tok) for tok in tokens):
            return False, _friendly(
                kind,
                "looks like random characters — please paste the real content.",
            )

    if _dominant_pattern_ratio(stripped) > _REPETITION_THRESHOLD:
        return False, _friendly(
            kind,
            "looks like repeated or random characters — please paste the real content.",
        )

    return True, None


def validate_prep_inputs(
    req: PrepRequest, *, cv_text: str | None = None
) -> tuple[bool, list[str]]:
    """返回 (ok, warnings)，仅简历和职位同时无效时 ok 为 False。

    优先校验已提取的 cv_text，未提供时使用 cv_url；公司名无效只追加警告。
    """
    warnings: list[str] = []

    cv_input = cv_text if cv_text is not None else req.cv_url
    cv_ok, cv_reason = assess_text(cv_input, kind="cv", min_len=_MIN_LEN_CV)
    jd_ok, jd_reason = assess_text(req.jd_text, kind="jd", min_len=_MIN_LEN_JD)
    company_ok, company_reason = assess_text(
        req.company, kind="company", min_len=_MIN_LEN_COMPANY
    )

    if not cv_ok and not jd_ok:
        reasons = [r for r in (cv_reason, jd_reason) if r]
        return False, reasons

    if not cv_ok and cv_reason:
        warnings.append(cv_reason)
    if not jd_ok and jd_reason:
        warnings.append(jd_reason)
    if not company_ok and company_reason:
        warnings.append(company_reason)

    return True, warnings
