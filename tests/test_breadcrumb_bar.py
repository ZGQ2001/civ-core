"""BreadcrumbBar：面包屑文本 + action 区增删。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from civ_core.ui.components.breadcrumb_bar import BAR_HEIGHT, BreadcrumbBar  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_construct() -> None:
    _ensure_app()
    b = BreadcrumbBar()
    assert b.height() == BAR_HEIGHT
    assert b.action_count() == 0


def test_breadcrumb_text() -> None:
    _ensure_app()
    b = BreadcrumbBar()
    b.set_breadcrumb("项目X", "绘曲线图")
    assert "项目X" in b._crumb.text()
    assert "绘曲线图" in b._crumb.text()
    # 空段跳过
    b.set_breadcrumb(None, "仅工具")
    assert b._crumb.text() == "仅工具"
    # 全空 → 空字符串
    b.set_breadcrumb(None, None)
    assert b._crumb.text() == ""


def test_action_add_clear() -> None:
    _ensure_app()
    b = BreadcrumbBar()
    btn1 = QPushButton("生成")
    btn2 = QPushButton("导出")
    b.add_action(btn1)
    b.add_action(btn2)
    assert b.action_count() == 2
    b.clear_actions()
    assert b.action_count() == 0
