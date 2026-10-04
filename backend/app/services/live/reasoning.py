"""Remove inline reasoning before streaming text reaches speech or captions."""

from __future__ import annotations

import re

_TAGS = ("<think>", "</think>", "<thinking>", "</thinking>")
_TAG = re.compile(r"</?(?:think|thinking)>", re.IGNORECASE)


class ReasoningFilter:
    """Keep tag prefixes across chunks; never flush an unfinished thought."""

    def __init__(self) -> None:
        self._buffer = ""
        self._depth = 0

    def feed(self, text: str) -> str:
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
        # A pending tag prefix may itself be the beginning of a thought.
        self._buffer = ""
        self._depth = 0
        return ""
