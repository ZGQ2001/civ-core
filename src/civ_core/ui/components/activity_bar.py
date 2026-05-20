"""ActivityBar：左侧 48px 工具切换栏（VSCode Activity Bar 风）。

布局（纵向）：
  ┌────┐
  │ T1 │ ← 顶部组：Explorer / Search / SCM 等普通工具
  │ T2 │
  │ T3 │
  │ T4 │
  │ .  │
  │ .  │
  │ .  │   stretch（自动占满中间）
  │ B1 │ ← 底部组：Accounts / Settings（gear icon）—— VSCode 风
  └────┘

按钮间用 QButtonGroup exclusive 互斥（同一时刻只有一个选中）。

Signals:
    current_tool_changed(str): 用户切换工具时发出（编程 set_current 也触发）。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QToolButton,
    QVBoxLayout,
)
from qfluentwidgets import FluentIcon

BAR_WIDTH = 48
BTN_SIZE = 40
ICON_SIZE = 22


class ActivityBar(QFrame):
    current_tool_changed = Signal(str)

    def __init__(
        self,
        items: Iterable[tuple[str, FluentIcon, str]] | None = None,
        parent=None,
    ) -> None:
        """Args:
        items: [(tool_name, icon, tooltip), ...]，按显示顺序排（全进顶部组）；
               用 add_tool / add_bottom_tool 可继续追加。
        """
        super().__init__(parent)
        self.setObjectName("activityBar")
        self.setFixedWidth(BAR_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout = layout

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        # 顶部组 + stretch + 底部组（VSCode 风分区）
        # stretch 在 _layout 中间，addStretch 返回的是 spacer item 没法精确索引；
        # 所以维护一个"stretch 在 layout 里的位置 index"
        self._stretch_index: int = 0
        # 先把可能的 items 全部 add 到顶部
        if items:
            for name, icon, tooltip in items:
                self.add_tool(name, icon, tooltip)
        # 然后加 stretch（位置变成当前最末，记下来）
        layout.addStretch(1)
        self._stretch_index = layout.count() - 1

    def _make_btn(self, name: str, icon: FluentIcon, tooltip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName(f"activityBtn_{name}")
        btn.setCheckable(True)
        btn.setToolTip(tooltip)
        btn.setIcon(icon.icon())
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setFixedSize(BAR_WIDTH, BTN_SIZE)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.toggled.connect(
            lambda checked, n=name: checked and self.current_tool_changed.emit(n)
        )
        self._group.addButton(btn)
        self._buttons[name] = btn
        return btn

    def add_tool(self, name: str, icon: FluentIcon, tooltip: str) -> QToolButton:
        """追加到顶部组（在 stretch 之前）。"""
        btn = self._make_btn(name, icon, tooltip)
        # stretch 在末尾时 _stretch_index = count-1；插入位置就是 stretch 之前
        insert_at = self._stretch_index if self._stretch_index else self._layout.count()
        self._layout.insertWidget(insert_at, btn)
        if self._stretch_index:
            self._stretch_index += 1
        return btn

    def add_bottom_tool(self, name: str, icon: FluentIcon, tooltip: str) -> QToolButton:
        """追加到底部组（在 stretch 之后）—— VSCode 的 settings/accounts 区。"""
        btn = self._make_btn(name, icon, tooltip)
        # 直接 addWidget 加到最末（stretch 之后）
        self._layout.addWidget(btn)
        return btn

    def set_current(self, name: str) -> None:
        btn = self._buttons.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def current(self) -> str | None:
        for name, btn in self._buttons.items():
            if btn.isChecked():
                return name
        return None

    def tools(self) -> list[str]:
        return list(self._buttons.keys())
