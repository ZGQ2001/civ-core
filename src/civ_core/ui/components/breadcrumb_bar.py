"""BreadcrumbBar：顶栏面包屑 + 主操作按钮容器（跨全宽）。

布局：[ 项目名 > 当前工具 ] ──────── [ 工具自定义按钮位 ]

各工具页切换时 shell 会清空 action 区并由新工具页 add_action 填入自己的按钮。
B1 阶段先保留这个容器接口；具体工具按钮接入留给 Step C / D。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

BAR_HEIGHT = 36


class BreadcrumbBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("breadcrumbBar")
        self.setFixedHeight(BAR_HEIGHT)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(8)

        self._crumb = QLabel(self)
        self._crumb.setObjectName("breadcrumbText")
        self._crumb.setStyleSheet("color: #B8BFC9; font-size: 12px;")
        h.addWidget(self._crumb)
        h.addStretch(1)

        # action 容器：每次 clear_actions 重建子布局更稳，但用单一容器布局直接 take/delete 也行
        self._actions = QWidget(self)
        self._actions_layout = QHBoxLayout(self._actions)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(6)
        h.addWidget(self._actions)

    # ── 面包屑 ──────────────────────────────────────────
    def set_breadcrumb(self, workspace: str | None, tool: str | None) -> None:
        """设置面包屑文本。空段会被跳过；都为空时清空。"""
        parts = [s for s in (workspace, tool) if s]
        self._crumb.setText("  ›  ".join(parts))

    # ── 主操作按钮 ──────────────────────────────────────────
    def clear_actions(self) -> None:
        """清空 action 区（切换工具时调用）。"""
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def add_action(self, button: QPushButton) -> None:
        """追加一个操作按钮到右侧 action 区。"""
        self._actions_layout.addWidget(button)

    def action_count(self) -> int:
        """当前 action 区按钮数（测试 + 调试用）。"""
        return self._actions_layout.count()
