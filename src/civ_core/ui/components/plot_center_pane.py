"""绘曲线图工具中栏的 Pivot 双 Tab 容器。

布局
====
  ┌──────────────────────────────────────────────┐
  │ [ 绘图参数 ] [ 预设设置 ]   ← Pivot           │
  ├──────────────────────────────────────────────┤
  │                                              │
  │   QStackedWidget 内容（由 Pivot 切换）        │
  │   ├─ tab "settings": PlotSettingsPanel       │
  │   └─ tab "preset"  : PresetFormPanel         │
  │                                              │
  └──────────────────────────────────────────────┘

为什么把这两个面板包在一起
==========================
原 plot_curves_view.py 的中栏直接是 PlotSettingsPanel；T-4 要在中栏加
"预设设置" Tab。Pivot 切换 + QStackedWidget 是 qfluentwidgets 的标准组合，
逻辑封装到一个组件里能让 plot_curves_view 保持简单（继续只管理三栏）。

对外 API：
  • settings_panel  —— 暴露 PlotSettingsPanel 实例（plot_curves_view 还要
                       拿它的 .settings 给 worker 用）
  • form_panel      —— 暴露 PresetFormPanel 实例（plot_curves_view 在选预设
                       和保存时都要联动）
  • show_form_tab() / show_settings_tab() —— 切到对应 Tab，左栏选预设时调
"""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import Pivot

from civ_core.configs.loader import AppConfig
from civ_core.ui.components.plot_settings_panel import PlotSettingsPanel
from civ_core.ui.components.preset_form_panel import PresetFormPanel
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# Pivot 的 routeKey —— 与 QStackedWidget 索引绑定。
# 用语义化 key 而不是 0/1 数字，便于调试日志可读
_TAB_SETTINGS = "settings"
_TAB_PRESET_FORM = "preset_form"


class PlotCenterPane(QWidget):
    """中栏 Pivot 容器：把"绘图参数"和"预设设置"包成两 Tab。

    本组件仅做"装两个面板 + Pivot 切换"。不知道左栏 / 右栏，也不直接读写
    PresetEntry —— 这两类联动由 plot_curves_view 在更高层组织。
    """

    def __init__(self, cfg: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("plotCenterPane")

        self._build_ui(cfg)
        self._wire_signals()
        log.debug("PlotCenterPane ready")

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_ui(self, cfg: AppConfig) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ── Pivot：顶部 Tab 切换条 ──
        self._pivot = Pivot(self)
        self._pivot.addItem(routeKey=_TAB_SETTINGS, text="绘图参数")
        self._pivot.addItem(routeKey=_TAB_PRESET_FORM, text="预设设置")
        outer.addWidget(self._pivot)

        # ── QStackedWidget：Pivot 切换的内容区 ──
        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack, 1)

        # 依 Pivot 添加的顺序，添加内容页：
        # index 0 → settings；index 1 → preset_form
        self.settings_panel = PlotSettingsPanel(cfg, self._stack)
        self.form_panel = PresetFormPanel(self._stack)
        self._stack.addWidget(self.settings_panel)
        self._stack.addWidget(self.form_panel)

        # 默认显示 "绘图参数"，与 Pivot 第一个 item 对齐
        self._pivot.setCurrentItem(_TAB_SETTINGS)
        self._stack.setCurrentIndex(0)

    def _wire_signals(self) -> None:
        # Pivot 切换 → QStackedWidget 跟着切
        self._pivot.currentItemChanged.connect(self._on_pivot_changed)

    # ── 公共 API ──────────────────────────────────────────────────
    def show_settings_tab(self) -> None:
        """切到"绘图参数"Tab。"""
        self._pivot.setCurrentItem(_TAB_SETTINGS)
        # currentItemChanged 信号会驱动 _on_pivot_changed → setCurrentIndex，
        # 但 setCurrentItem 在某些版本里不一定 emit；保险起见显式同步一次
        self._stack.setCurrentIndex(0)

    def show_form_tab(self) -> None:
        """切到"预设设置"Tab（左栏单击预设时调）。"""
        self._pivot.setCurrentItem(_TAB_PRESET_FORM)
        self._stack.setCurrentIndex(1)

    def current_tab(self) -> str:
        """返回当前 Tab 的 routeKey（测试 / 调试用）。"""
        return _TAB_SETTINGS if self._stack.currentIndex() == 0 else _TAB_PRESET_FORM

    # ── 内部 ──────────────────────────────────────────────────────
    def _on_pivot_changed(self, route_key: str) -> None:
        """Pivot 切换 → QStackedWidget 跟着切。"""
        if route_key == _TAB_SETTINGS:
            self._stack.setCurrentIndex(0)
        elif route_key == _TAB_PRESET_FORM:
            self._stack.setCurrentIndex(1)
        else:
            log.warning("未知的 Pivot routeKey: %r，忽略", route_key)
            return
        log.debug("Pivot 切到：%s", route_key)
