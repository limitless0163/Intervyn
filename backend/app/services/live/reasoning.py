"""流式文本进入语音和字幕前清除内联推理块。"""

from __future__ import annotations

import re

_TAGS = ("<think>", "</think>", "<thinking>", "</thinking>")
_TAG = re.compile(r"</?(?:think|thinking)>", re.IGNORECASE)


class ReasoningFilter:
    """跨分块保留未完整的标签前缀，并跟踪推理深度；结束时不输出残留内容。"""

    def __init__(self) -> None:
        self._buffer = ""
        self._depth = 0

    def feed(self, text: str) -> str:
        """返回当前分块已确认的公开文本；不完整标签前缀留待下一分块判断。"""
        self._buffer += text
        visible: list[str] = []
        while self._buffer:
            match = _TAG.search(self._buffer)
            if match:
                if not self._depth:
                    visible.append(self._buffer[: match.start()])
                if match.group().startswith("</"):
                    self._depth = max(0, self._depth - 1)
                else:
                    self._depth += 1
                self._buffer = self._buffer[match.end() :]
                continue

            lowered = self._buffer.lower()
            keep = max(
                (
                    size
                    for tag in _TAGS
                    for size in range(1, len(tag))
                    if lowered.endswith(tag[:size])
                ),
                default=0,
            )
            if not self._depth:
                visible.append(self._buffer[:-keep] if keep else self._buffer)
            self._buffer = self._buffer[-keep:] if keep else ""
            break
        return "".join(visible)

    def finish(self) -> str:
        # 未完整的标签前缀可能是推理开头，结束时直接丢弃以免泄露。
        self._buffer = ""
        self._depth = 0
        return ""
