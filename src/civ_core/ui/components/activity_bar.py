"""ActivityBar：左侧 48px 工具切换栏（VSCode 风）。

为什么独立成组件：
  - shell 的常驻第一栏，跨工具页不重建；切工具是发信号让 stacked 换页
  - 工具列表由 shell 装配时注入，本组件只管按钮渲染 / 选中态 / 信号
  - 按钮用 QButtonGroup 的 exclusive 模式保证"同时只有一个高亮"
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

# 模块级常量：栏宽 + 按钮尺寸（保持 VSCode 接近的视觉比例）
BAR_WIDTH = 48
BTN_SIZE = 40
ICON_SIZE = 22


class ActivityBar(QFrame):
    """纵向工具切换栏。

    Signals:
        current_tool_changed(str): 用户点选工具名时发出。
    """

    current_tool_changed = Signal(str)

    def __init__(
        self,
        items: Iterable[tuple[str, FluentIcon, str]] | None = None,
        parent=None,
    ) -> None:
        """Args:
        items: [(tool_name, icon, tooltip), ...]，按显示顺序排列；可后续 add_tool 追加。
        """
        super().__init__(parent)
        self.setObjectName("activityBar")
        self.setFixedWidth(BAR_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout = layout

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        if items:
            for name, icon, tooltip in items:
                self.add_tool(name, icon, tooltip)

        # 末尾留一个 stretch 让所有按钮顶到上方（即便后续 add_tool 也仍在 stretch 之前）
        layout.addStretch(1)

    def add_tool(self, name: str, icon: FluentIcon, tooltip: str) -> QToolButton:
        """追加一个工具按钮。"""
        btn = QToolButton(self)
        btn.setObjectName(f"activityBtn_{name}")
        btn.setCheckable(True)
        btn.setToolTip(tooltip)
        btn.setIcon(icon.icon())
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setFixedSize(BTN_SIZE, BTN_SIZE)
        # 用 toggled 而非 clicked：QButtonGroup exclusive 切换时 setChecked 也会触发，
        # 这样外部调 set_current 也能同步发信号
        btn.toggled.connect(
            lambda checked, n=name: checked and self.current_tool_changed.emit(n)
        )
        self._group.addButton(btn)
        self._buttons[name] = btn
        # 插到末尾 stretch 之前；首次构造时 stretch 还没加，count() 为 0，insertWidget 等价于 addWidget
        insert_at = max(0, self._layout.count() - 1)
        self._layout.insertWidget(insert_at, btn)
        return btn

    def set_current(self, name: str) -> None:
        """编程切换当前工具（不会重复触发信号，QToolButton.setChecked 已有去重）。"""
        btn = self._buttons.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def current(self) -> str | None:
        """返回当前选中的工具名；都没选则 None。"""
        for name, btn in self._buttons.items():
            if btn.isChecked():
                return name
        return None

    def tools(self) -> list[str]:
        """按添加顺序返回所有已注册的工具名。"""
        return list(self._buttons.keys())
