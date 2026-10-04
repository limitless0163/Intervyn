"""实时语音服务的离线安全入口，仅导出不依赖 LiveKit 的状态逻辑。

需要 livekit 扩展的智能体和工作进程由调用方按需导入，避免离线测试导入失败。
"""

from __future__ import annotations

from . import state

__all__ = ["state"]
