"""BreadcrumbBar：顶栏极简面包屑（VSCode 风）。

只显示路径文本「项目名 / 当前工具」，无按钮、无 emoji。
工具页自定义主操作按钮通过 add_action 接入右侧 trailing 区（切工具时 shell 清空）。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

BAR_HEIGHT = 28


class BreadcrumbBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("breadcrumbBar")
        self.setFixedHeight(BAR_HEIGHT)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(6)

        # leading 区保留 API，shell 默认不用（VSCode 顶栏不放大按钮）
        self._leading = QWidget(self)
        self._leading_layout = QHBoxLayout(self._leading)
        self._leading_layout.setContentsMargins(0, 0, 0, 0)
        self._leading_layout.setSpacing(2)
        h.addWidget(self._leading)

        self._crumb = QLabel(self)
        self._crumb.setObjectName("breadcrumbText")
        h.addWidget(self._crumb)
        h.addStretch(1)

        # trailing：工具页主操作按钮（切工具时由 shell 清空 + 新页填充）
        self._actions = QWidget(self)
        self._actions_layout = QHBoxLayout(self._actions)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(4)
        h.addWidget(self._actions)

    def set_breadcrumb(self, workspace: str | None, tool: str | None) -> None:
        parts = [s for s in (workspace, tool) if s]
        self._crumb.setText("  /  ".join(parts))

    # ── trailing actions ──────────────────────────────────
    def clear_actions(self) -> None:
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def add_action(self, button: QPushButton) -> None:
        self._actions_layout.addWidget(button)

    def action_count(self) -> int:
        return self._actions_layout.count()

    # ── leading actions（保留 API，VSCode 风默认不用） ───────
    def add_leading_action(self, button: QPushButton) -> None:
        self._leading_layout.addWidget(button)

    def leading_count(self) -> int:
        return self._leading_layout.count()
