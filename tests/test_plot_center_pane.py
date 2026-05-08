"""PlotCenterPane（中栏 Pivot 双 Tab 容器）的 smoke 测试。

验证：
  • 构造时同时有 settings_panel / form_panel 两个子组件
  • show_settings_tab / show_form_tab 切换 routeKey
  • current_tab() 返回当前选中的 routeKey
  • Pivot 切换信号能驱动 QStackedWidget（手工触发 currentItemChanged）

不测的内容：渲染像素、Pivot 视觉样式（依赖 qfluentwidgets）。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.configs.loader import load_config  # noqa: E402
from civ_core.ui.components.plot_center_pane import PlotCenterPane  # noqa: E402
from civ_core.ui.components.plot_settings_panel import PlotSettingsPanel  # noqa: E402
from civ_core.ui.components.preset_form_panel import PresetFormPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def pane(qapp: QApplication) -> PlotCenterPane:
    cfg = load_config()
    p = PlotCenterPane(cfg)
    yield p
    p.deleteLater()


class TestPlotCenterPane:
    def test_construction_has_both_subpanels(self, pane: PlotCenterPane) -> None:
        assert isinstance(pane.settings_panel, PlotSettingsPanel)
        assert isinstance(pane.form_panel, PresetFormPanel)

    def test_default_tab_is_settings(self, pane: PlotCenterPane) -> None:
        """构造完成时，默认显示"绘图参数"Tab。"""
        assert pane.current_tab() == "settings"

    def test_show_form_tab_switches(self, pane: PlotCenterPane) -> None:
        pane.show_form_tab()
        assert pane.current_tab() == "preset_form"

    def test_show_settings_tab_switches_back(
        self, pane: PlotCenterPane
    ) -> None:
        pane.show_form_tab()
        pane.show_settings_tab()
        assert pane.current_tab() == "settings"

    def test_pivot_signal_drives_stack(self, pane: PlotCenterPane) -> None:
        """Pivot 的 currentItemChanged 信号触发后，QStackedWidget 跟着切。"""
        # 直接在 Pivot 上 emit currentItemChanged，模拟用户点击 Tab
        pane._pivot.currentItemChanged.emit("preset_form")
        assert pane.current_tab() == "preset_form"
        pane._pivot.currentItemChanged.emit("settings")
        assert pane.current_tab() == "settings"

    def test_unknown_route_key_is_ignored(
        self, pane: PlotCenterPane
    ) -> None:
        """未知 routeKey → 保持原状态，不崩。"""
        pane.show_settings_tab()
        pane._pivot.currentItemChanged.emit("not_a_real_tab")
        # 仍停在 settings
        assert pane.current_tab() == "settings"
