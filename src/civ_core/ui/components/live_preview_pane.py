"""实时预览面板（L-1 占位 / L-2 实装）。

L-1 Step 1：仅作为右栏占位，确认两栏 QSplitter 布局正确。
界面只有一行说明文字，提示开发者本面板在 L-2（实时渲染管线）阶段才会接入。

L-2 计划实装的对外接口（与 PROGRESS.md 一致）：
  • set_preset(entry)
  • set_data_source(path)
  • request_redraw()
内部用 QTimer.singleShot(300ms) 防抖；渲到内存 BytesIO → QPixmap，避免反复落盘。

为什么先做占位：
  • L-1 只动布局骨架，不动渲染逻辑；先让 view 能两栏拼出来才能继续往下挂面板
  • 占位 widget 留 objectName，方便测试 / DevTools 定位
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel


class LivePreviewPane(QWidget):
    """实时预览面板。当前为占位实现（仅显示等待提示）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName 用于 qfluentwidgets 路由 / 测试定位
        self.setObjectName("livePreviewPane")
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title = SubtitleLabel("实时预览", self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = BodyLabel(
            "（L-2 阶段接入实时渲染管线：参数变化后 300ms 防抖重绘）",
            self,
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
