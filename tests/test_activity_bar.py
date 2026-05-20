"""ActivityBar：smoke + 信号 + 选中态。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import FluentIcon  # noqa: E402

from civ_core.ui.components.activity_bar import BAR_WIDTH, ActivityBar  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_construct_with_items() -> None:
    _ensure_app()
    bar = ActivityBar(
        [
            ("plot_curves", FluentIcon.MARKET, "绘曲线图"),
            ("settings", FluentIcon.SETTING, "设置"),
        ]
    )
    assert bar.width() == BAR_WIDTH
    assert bar.tools() == ["plot_curves", "settings"]


def test_set_current_emits_signal(qtbot) -> None:
    _ensure_app()
    bar = ActivityBar(
        [
            ("a", FluentIcon.HOME, "A"),
            ("b", FluentIcon.SETTING, "B"),
        ]
    )
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.current_tool_changed, timeout=500) as sig:
        bar.set_current("b")
    assert sig.args == ["b"]
    assert bar.current() == "b"


def test_exclusive_toggle(qtbot) -> None:
    """同一时刻只能有一个工具激活。"""
    _ensure_app()
    bar = ActivityBar(
        [
            ("a", FluentIcon.HOME, "A"),
            ("b", FluentIcon.SETTING, "B"),
        ]
    )
    qtbot.addWidget(bar)
    bar.set_current("a")
    bar.set_current("b")
    assert bar.current() == "b"
    # 重复设置同一工具不应再触发信号（QButtonGroup 已去重）
    bar.set_current("b")
    assert bar.current() == "b"


def test_add_tool_after_construct() -> None:
    _ensure_app()
    bar = ActivityBar()
    bar.add_tool("late", FluentIcon.ROBOT, "晚加")
    assert "late" in bar.tools()
