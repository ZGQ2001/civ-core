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

4. **风琴菜单切换 expand 时标题文字不"跳动"**
   bug：ToolButton.setText(f"{arrow}  {title}") 模式下 `▾`(U+25BE small white)
       和 `▸`(U+25B8 small black) 字面宽度+字形粗细都不同，切换时整段文本左右晃。
   断言：_SectionHeader 内部箭头 QLabel 宽度恒定（fixedWidth=14），且 expand /
        collapse 切换前后 title QLabel 的 x 起点完全相等。

5. **展开分组时 splitter 左栏被内部 sizeHint 撑大**
   bug：DoubleSpinBox 的默认 setRange(-1e9, 1e9) 让其 sizeHint ≈ 324px（按最长
       数字串算宽）；`_RangeTrio` 一行横排 3 个 SpinBox + label，加上 CurvesEditor
       等内部组件，让 content widget 的 minimumSizeHint ≈ 342px。当 splitter
       左栏宽 < 342 时，content 被自身 minimumSize 撑到 342，按钮 / LineEdit 跟着
       拉伸到 342 → 但显示区只有 splitter 给的宽度 → 内容溢出被截、字位移。
   断言：QScrollArea 内的 content widget 的 minimumSizeHint().width() ≤ 220，
        无论分组展开/折叠状态如何 —— 通过给 DoubleSpinBox 设 setMinimumWidth(50)
        让控件能压缩到容器宽度。
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
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """让 PresetAccordionPanel._make_settings 走 tmp ini，避免污染。"""
    ini_path = tmp_path / "settings.ini"

    from civ_core.ui.components import preset_accordion_panel as pap

    def fake_make_settings(self: Any) -> QSettings:
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr(pap.PresetAccordionPanel, "_make_settings", fake_make_settings)
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
                f"image_label minimumSize={ms.width()}x{ms.height()} 太大，splitter 右拖会被它顶住"
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
                f"主窗口 minWidth={ms.width()} ≥ 启动宽度 {startup_w}，用户无法把窗口缩小"
            )
            assert ms.height() < startup_h, (
                f"主窗口 minHeight={ms.height()} ≥ 启动高度 {startup_h}，用户无法把窗口缩小"
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
                "启动后预设默认未选中 —— 用户选完 Excel 点生成会被提示「请先选预设」"
            )
        finally:
            panel.deleteLater()

    def test_section_header_arrow_fixed_width_and_title_no_jitter(self, qapp: QApplication) -> None:
        """风琴菜单 expand/collapse 切换时标题不能跳动。

        断言两件事：
          1. 箭头 QLabel 宽度恒定（=14px，由 setFixedWidth 保证）
          2. expand → collapse → expand 切换前后，title QLabel 的 x 坐标完全相等
        """
        from civ_core.ui.components.preset_accordion_panel import (
            _CollapsibleSection,
        )

        section = _CollapsibleSection("测试分组", collapsible=True, initially_expanded=True)
        try:
            # 必须先 show 才会有真实布局尺寸（offscreen 模式下也成立）
            section.resize(300, 100)
            section.show()
            qapp.processEvents()

            arrow = section._header._arrow_label
            title = section._header._title_label

            w_before = arrow.width()
            x_title_before = title.x()

            section._toggle()  # 收起
            qapp.processEvents()
            w_collapsed = arrow.width()
            x_title_collapsed = title.x()

            section._toggle()  # 再展开
            qapp.processEvents()
            w_after = arrow.width()
            x_title_after = title.x()

            assert w_before == w_collapsed == w_after, (
                f"箭头宽度不恒定：expand={w_before}, collapse={w_collapsed}, "
                f"expand={w_after} —— 这就是用户看到的「标题跳动」根因"
            )
            assert x_title_before == x_title_collapsed == x_title_after, (
                f"标题 x 起点抖动：expand x={x_title_before}, "
                f"collapse x={x_title_collapsed}, expand x={x_title_after}"
            )
        finally:
            section.deleteLater()

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


# ──────────────────────────────────────────────────────────────────
# Bug 5：splitter 左栏被内部 sizeHint 撑大
# ──────────────────────────────────────────────────────────────────
class TestPanelMinSizeHintNotInflatedByGroups:
    """PresetAccordionPanel 的 minimumSizeHint 不能被内部分组撑大。

    用户场景：展开"坐标轴"分组时，里面 _RangeTrio 一行横排 min/max/step
    三个 SpinBox + label，累加 minimumSizeHint ≈ 400-500px。如果 panel
    自身把这个 hint 透传给 QSplitter，splitter 会强制左栏 ≥ 该宽度 →
    "保存为我的预设"按钮被拉伸 / 字体位移 / 右栏被挤压。

    修复方式：PresetAccordionPanel 覆盖 minimumSizeHint() 横向上限 200，
    让 splitter 完全接管左栏宽度，内部 _RangeTrio 通过 SpinBox 的
    minimumWidth(60) 实现窄宽下也能完整显示。
    """

    def test_min_size_hint_width_capped_when_collapsed(
        self, qapp: QApplication, tmp_settings: Path
    ) -> None:
        """所有分组都收起时 minSizeHint.width 应 ≤ 200。"""
        from civ_core.ui.components.preset_accordion_panel import PresetAccordionPanel

        panel = PresetAccordionPanel()
        try:
            msh = panel.minimumSizeHint()
            assert msh.width() <= 200, (
                f"折叠态 minSizeHint.width={msh.width()} > 200，"
                "splitter 会被撑大"
            )
        finally:
            panel.deleteLater()

    def test_min_size_hint_width_capped_when_axis_expanded(
        self, qapp: QApplication, tmp_settings: Path
    ) -> None:
        """展开"坐标轴"分组后 minSizeHint.width 仍应 ≤ 200（用户报告的核心场景）。"""
        from civ_core.ui.components.preset_accordion_panel import PresetAccordionPanel

        panel = PresetAccordionPanel()
        try:
            # 坐标轴分组默认收起 → 这里显式 toggle 展开
            panel._sec_axis._toggle()
            qapp.processEvents()
            msh = panel.minimumSizeHint()
            assert msh.width() <= 200, (
                f"坐标轴展开后 minSizeHint.width={msh.width()} > 200，"
                "splitter 会被 _RangeTrio 一行横排撑大 → 「保存为我的预设」按钮位移"
            )
        finally:
            panel.deleteLater()

    def test_min_size_hint_width_capped_when_all_groups_expanded(
        self, qapp: QApplication, tmp_settings: Path
    ) -> None:
        """所有分组（含数据源 / 曲线定义 / 坐标轴 / 样式 / 输出）全展开时也不超 200。"""
        from civ_core.ui.components.preset_accordion_panel import PresetAccordionPanel

        panel = PresetAccordionPanel()
        try:
            # 把 5 个可折叠分组都打开（_sec_preset 不可折叠）
            for sec_name in (
                "_sec_data",
                "_sec_curves",
                "_sec_axis",
                "_sec_style",
                "_sec_out",
            ):
                sec = getattr(panel, sec_name)
                if not sec.is_expanded():
                    sec._toggle()
            qapp.processEvents()
            msh = panel.minimumSizeHint()
            assert msh.width() <= 200, (
                f"全展开后 minSizeHint.width={msh.width()} > 200，"
                "压力测试不通过"
            )
        finally:
            panel.deleteLater()
