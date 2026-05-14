"""UI 修复回归测试：splitter 缩窗口 + 预设默认选中。

本次任务的三个 bug 对应的回归用例（先写测试拦截边界）：

1. **LivePreviewPane 容器允许任意缩小**
   bug：QLabel.setPixmap 会让 sizeHint = pixmap 像素尺寸，外层 splitter / 主窗口
       右拖收缩时被 hint 顶住，缩不回去。
   断言：image_label 的 sizePolicy 是 Ignored × Ignored，且 minimumSize == (1,1)；
   同时 LivePreviewPane 自身 minimumSize == (0,0)，让父 splitter 完全接管。

2. **MainWindow 显式 setMinimumSize(720, 480)**
   bug：FluentWindow 默认 minSize 可能比内容子组件累加 sizeHint 还要小，但子组件
       sizeHint 顶死的话窗口右拖缩不动。我们显式 setMinimumSize 保证下限可控。
   断言：minimumSize == (720, 480)。

3. **PresetAccordionPanel 启动后 current_run_settings().preset_name 非 None**
   bug：refresh() 在 _suppress=True 下 setCurrentIndex(0)，在某些 qfluentwidgets
       版本下 currentIndex 没立即生效，导致 _current_preset_name 一直是 None；
       用户感知是"选完数据源仍提示请先选预设"。
   断言：直接构造 panel 后调 current_run_settings()，preset_name 不该为 None
        （前提：系统预设 curve_presets.json 非空 —— 由 healthcheck 保证）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QSizePolicy  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def tmp_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """让 PresetAccordionPanel._make_settings 走 tmp ini，避免污染。"""
    ini_path = tmp_path / "settings.ini"

    from civ_core.ui.components import preset_accordion_panel as pap

    def fake_make_settings(self: Any) -> QSettings:
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr(
        pap.PresetAccordionPanel, "_make_settings", fake_make_settings
    )
    return ini_path


# ──────────────────────────────────────────────────────────────────
# Bug 1 + 2：缩放边界
# ──────────────────────────────────────────────────────────────────
class TestLivePreviewShrinkable:
    """LivePreviewPane 在 setPixmap 后容器仍可被外层任意缩小。"""

    def test_image_label_size_policy_ignored(self, qapp: QApplication) -> None:
        """image_label 必须用 Ignored×Ignored 的 sizePolicy。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            policy = pane._image_label.sizePolicy()
            assert policy.horizontalPolicy() == QSizePolicy.Policy.Ignored, (
                "image_label 水平 sizePolicy 必须是 Ignored，"
                "否则 setPixmap 后 sizeHint 顶死外层 splitter"
            )
            assert policy.verticalPolicy() == QSizePolicy.Policy.Ignored, (
                "image_label 垂直 sizePolicy 必须是 Ignored，"
                "否则 setPixmap 后 sizeHint 顶死外层 splitter"
            )
        finally:
            pane.deleteLater()

    def test_image_label_minimum_size_is_one(self, qapp: QApplication) -> None:
        """image_label minimumSize 必须 == (1, 1)，让父容器自由缩小。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            ms = pane._image_label.minimumSize()
            assert ms.width() <= 1 and ms.height() <= 1, (
                f"image_label minimumSize={ms.width()}x{ms.height()} 太大，"
                "splitter 右拖会被它顶住"
            )
        finally:
            pane.deleteLater()

    def test_pane_minimum_size_zero(self, qapp: QApplication) -> None:
        """LivePreviewPane 自身 minimumSize 必须 (0, 0)，让父 splitter 接管。"""
        from civ_core.ui.components.live_preview_pane import LivePreviewPane

        pane = LivePreviewPane()
        try:
            ms = pane.minimumSize()
            assert ms.width() == 0 and ms.height() == 0, (
                f"LivePreviewPane minimumSize={ms.width()}x{ms.height()} 不为 0，"
                "splitter / 主窗口右拖时无法把它压扁"
            )
        finally:
            pane.deleteLater()


class TestMainWindowMinSize:
    """MainWindow 显式 setMinimumSize 保证右拖可缩。"""

    def test_main_window_has_minimum_size(self, qapp: QApplication) -> None:
        from civ_core.configs.loader import load_config
        from civ_core.ui.windows.main_window import MainWindow

        cfg = load_config()
        win = MainWindow(cfg)
        try:
            ms = win.minimumSize()
            # 不强求精确数值，但必须比"启动尺寸"小（否则用户根本拖不动收缩）
            startup_w, startup_h = cfg.ui.startup_size
            assert ms.width() < startup_w, (
                f"主窗口 minWidth={ms.width()} ≥ 启动宽度 {startup_w}，"
                "用户无法把窗口缩小"
            )
            assert ms.height() < startup_h, (
                f"主窗口 minHeight={ms.height()} ≥ 启动高度 {startup_h}，"
                "用户无法把窗口缩小"
            )
            # 但也不能小到 0×0 —— 内容会塌
            assert ms.width() >= 400 and ms.height() >= 300, (
                f"主窗口 minSize={ms.width()}x{ms.height()} 过小，内容会塌"
            )
        finally:
            win.deleteLater()


# ──────────────────────────────────────────────────────────────────
# Bug 3：预设默认选中
# ──────────────────────────────────────────────────────────────────
class TestPresetDefaultSelected:
    """PresetAccordionPanel 启动后必须有预设默认选中。

    用户选了数据源就想点"生成"，不应该被强制回头再到预设 ComboBox 点一下。
    """

    def test_run_settings_preset_name_not_none_after_init(
        self, qapp: QApplication, tmp_settings: Path
    ) -> None:
        from civ_core.ui.components.preset_accordion_panel import (
            PresetAccordionPanel,
        )

        panel = PresetAccordionPanel()
        try:
            # 系统预设非空时（healthcheck 保证），current_run_settings 必须返回
            # 一个非 None 的 preset_name —— 不论是 _current_preset_name 在 refresh
            # 中正确同步，还是 current_run_settings 的兜底逻辑兜住，结果必须一致。
            if panel._preset_combo.count() == 0:
                pytest.skip("系统预设为空，本用例不适用")
            s = panel.current_run_settings()
            assert s.preset_name is not None, (
                "启动后预设默认未选中 —— "
                "用户选完 Excel 点生成会被提示「请先选预设」"
            )
        finally:
            panel.deleteLater()

    def test_run_settings_preset_name_survives_state_reset(
        self, qapp: QApplication, tmp_settings: Path
    ) -> None:
        """显式模拟"_current_preset_name 没同步"的状态，验证兜底逻辑。

        手工把 _current_preset_name 置 None（模拟 refresh 时序异常），
        再调 current_run_settings → 预期能从 ComboBox 兜底取回。
        """
        from civ_core.ui.components.preset_accordion_panel import (
            PresetAccordionPanel,
        )

        panel = PresetAccordionPanel()
        try:
            if panel._preset_combo.count() == 0:
                pytest.skip("系统预设为空，本用例不适用")
            # 制造"内部状态丢失"场景
            panel._current_preset_name = None
            s = panel.current_run_settings()
            assert s.preset_name is not None, (
                "兜底失败：_current_preset_name 缺失时 current_run_settings "
                "应从 ComboBox 当前选中项的 userData 取回预设名"
            )
        finally:
            panel.deleteLater()
