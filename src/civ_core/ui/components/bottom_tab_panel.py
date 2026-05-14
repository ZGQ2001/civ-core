"""底栏多 Tab 面板（L-4 实装）—— 把日志面板和数据源 Tab 整合到一起。

布局
====
  ┌──────────────────────────────────────────────────────────┐
  │ ▼  [日志] [数据源]                                        │  ← 工具栏
  ├──────────────────────────────────────────────────────────┤
  │ <当前 Tab 的内容（折叠时整个区块隐藏）>                    │
  └──────────────────────────────────────────────────────────┘

为什么这样设计
==============
  • 底部空间宝贵：单 LogPanel 用过头，再加数据源就要再叠一行
  • Tab 切换比"两个折叠面板叠在一起"省空间且符合直觉
  • LogPanel 自带 toggle 按钮 → 在本面板里隐藏，让 BottomTabPanel 的
    整体 toggle 接管折叠（避免双重折叠的视觉混乱）
  • DataSourcePane 直接作为 Tab 2 嵌入，对外暴露 row_highlighted 信号

接入要点（在 view 里）
======================
  bottom = BottomTabPanel(parent)
  bridge = get_qt_bridge()
  bridge.record_emitted.connect(bottom.log_panel.on_record)
  bottom.data_source_pane.row_highlighted.connect(live_preview.highlight_row)
  bottom.collapse_changed.connect(<view 的持久化逻辑>)
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import Pivot, TransparentToolButton

from civ_core.ui.components.data_source_pane import DataSourcePane
from civ_core.ui.components.log_panel import LogPanel
from civ_core.ui.components.thumbnail_pane import ThumbnailPane

_TAB_LOG = "log"
_TAB_DATA = "data"
_TAB_THUMB = "thumb"


class BottomTabPanel(QWidget):
    """底栏：日志 / 数据源两 Tab + 整体折叠按钮。"""

    # 折叠态翻转时发出；view 可据此把状态写到 QSettings
    collapse_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bottomTabPanel")
        # 显式允许窄宽：防止 DataSourcePane 内表格内容把整个面板撑大，
        # 进而把右栏 / 主水平 splitter / 主窗口都拉过屏幕宽度
        self.setMinimumWidth(0)

        # 默认折叠（与原 LogPanel 一致，避免开屏一堆日志干扰）
        self._collapsed = True

        # 子组件
        self.log_panel = LogPanel(self)
        # LogPanel 内部 toggle 按钮在本面板内多余，隐藏；让外层 toggle 接管
        self.log_panel._toggle_btn.setVisible(False)
        # 让 LogPanel 内部 text 一直可见（折叠由 BottomTabPanel 控制 stacked）
        self.log_panel.set_collapsed(False)

        self.data_source_pane = DataSourcePane(self)
        self.thumbnail_pane = ThumbnailPane(self)

        self._build_layout()
        self._apply_collapsed_state()

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 工具栏：整体 toggle + Tab 切换 ──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        toolbar.setSpacing(8)

        self._toggle_btn = TransparentToolButton(self)
        self._toggle_btn.setText("▶")
        self._toggle_btn.setToolTip("展开 / 折叠底部面板")
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        toolbar.addWidget(self._toggle_btn)

        # Pivot：日志 / 数据源 / 缩略图 三项
        self._pivot = Pivot(self)
        self._pivot.addItem(_TAB_LOG, "日志")
        self._pivot.addItem(_TAB_DATA, "数据源")
        self._pivot.addItem(_TAB_THUMB, "缩略图")
        self._pivot.setCurrentItem(_TAB_LOG)
        self._pivot.currentItemChanged.connect(self._on_tab_changed)
        toolbar.addWidget(self._pivot)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        # ── 主体：QStackedWidget（顺序与 Pivot tab key 对应：log/data/thumb） ──
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.log_panel)
        self._stack.addWidget(self.data_source_pane)
        self._stack.addWidget(self.thumbnail_pane)
        outer.addWidget(self._stack, 1)

    # ── 公共 API ─────────────────────────────────────────────────
    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_collapsed_state()
        self.collapse_changed.emit(collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def show_log_tab(self) -> None:
        self._pivot.setCurrentItem(_TAB_LOG)

    def show_data_tab(self) -> None:
        self._pivot.setCurrentItem(_TAB_DATA)

    def show_thumb_tab(self) -> None:
        self._pivot.setCurrentItem(_TAB_THUMB)

    def current_tab(self) -> str:
        idx = self._stack.currentIndex()
        if idx == 0:
            return _TAB_LOG
        if idx == 1:
            return _TAB_DATA
        return _TAB_THUMB

    # ── 内部 ──────────────────────────────────────────────────────
    def _apply_collapsed_state(self) -> None:
        self._stack.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")

    def _on_toggle_clicked(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _on_tab_changed(self, key: str) -> None:
        # 三档 tab key 与 stack index 一一对应（与 addWidget 顺序一致）
        idx_map = {_TAB_LOG: 0, _TAB_DATA: 1, _TAB_THUMB: 2}
        self._stack.setCurrentIndex(idx_map.get(key, 0))
        # 切到内容 Tab 时如果是折叠态，自动展开（更符合用户预期）
        if self._collapsed:
            self.set_collapsed(False)
