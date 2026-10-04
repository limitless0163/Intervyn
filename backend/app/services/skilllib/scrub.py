"""技能正文的个人信息清理；草稿写入前和正式发布前都需执行。

用姓名列表及保守正则替换姓名、邮箱和电话，不保证识别所有形式的个人信息。
"""

from __future__ import annotations

import re

# 邮箱规则只覆盖常见形式，避免过度匹配。
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# 电话允许常见分隔符，至少七位数字以免误删年份等短数字。
_PHONE_RE = re.compile(
    r"(?<![\w.])"  # 避免在单词中间或小数内部起始匹配。
    r"\+?\d[\d\s().-]{5,}\d"  # 首尾必须为数字，中间允许分隔符。
    r"(?![\w.])"
)


def _digit_count(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _scrub_phones(text: str) -> str:
    """只替换至少七位数字的电话形态匹配，保留误匹配的短数字。"""
    def _repl(m: re.Match[str]) -> str:
        return "[phone]" if _digit_count(m.group(0)) >= 7 else m.group(0)

    return _PHONE_RE.sub(_repl, text)


def scrub_pii(text: str, *, names: list[str]) -> str:
    """用 [candidate]、[email] 和 [phone] 替换已知姓名及匹配的联系方式。

    姓名按整词、忽略大小写匹配；电话至少含七位数字，重复清理不改变已替换内容。
    """
    out = text

    # 姓名按长度降序优先替换，避免先替换短名字后残留姓氏或名字片段。
    for name in sorted({n.strip() for n in names if n and n.strip()}, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        out = pattern.sub("[candidate]", out)

    out = _EMAIL_RE.sub("[email]", out)
    out = _scrub_phones(out)
    return out
