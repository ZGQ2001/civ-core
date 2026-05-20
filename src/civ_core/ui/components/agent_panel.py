"""AgentPanel：右侧 Agent 占位空壳（B1 阶段只做视觉占位）。

UI-4 阶段会接入 Claude API tool_use + 流式输出；本组件先保留位置 + 提示文字，
让用户看见"功能位"已经留好。最小 API：set_workspace(Path) 供 shell 同步当前工作区
（未来 agent 会基于工作区上下文工作）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

DEFAULT_WIDTH = 260


class AgentPanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("agentPanel")
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Agent", self)
        title.setObjectName("agentPanelTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #8B92A0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("AI 助手位（即将接入）", self)
        hint.setObjectName("agentPanelHint")
        hint.setStyleSheet("font-size: 11px; color: #5B6573;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch(1)

        self._workspace: Path | None = None

    def set_workspace(self, workspace: Path) -> None:
        """记录当前工作区路径，供未来 agent 上下文使用；当前只存不展示。"""
        self._workspace = workspace

    def workspace(self) -> Path | None:
        return self._workspace
