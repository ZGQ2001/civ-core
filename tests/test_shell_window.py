"""ShellWindow + initial_workspace：构造 + 空状态 + 工作区加载 + 工具切换。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.configs.loader import load_config  # noqa: E402
from civ_core.infra_io import workspace_settings as ws  # noqa: E402
from civ_core.infra_io.workspace_scaffold import create_standard_structure  # noqa: E402
from civ_core.ui.windows import shell_window as sw  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_settings(tmp_path, monkeypatch) -> None:
    """把 workspace_settings 的 QSettings 走临时目录，避免污染用户家目录。"""
    ini = tmp_path / "ws.ini"
    monkeypatch.setattr(
        ws,
        "_make_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def test_initial_workspace_returns_cached(tmp_path, monkeypatch) -> None:
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    workspace = tmp_path / "cached_ws"
    create_standard_structure(workspace)
    ws.save_last_workspace(workspace)
    assert sw.initial_workspace() == workspace


def test_initial_workspace_none_when_unset(tmp_path, monkeypatch) -> None:
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    ws.clear_last_workspace()
    assert sw.initial_workspace() is None


def test_shell_construct_with_workspace(tmp_path, monkeypatch) -> None:
    """传入有效 workspace → 文件树自动加载，empty state 不显示。"""
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    workspace = tmp_path / "ws_shell"
    create_standard_structure(workspace)

    cfg = load_config()
    win = sw.ShellWindow(cfg, workspace)
    try:
        # 核心组件就位（Agent 侧栏 B1 阶段已移除）
        for attr in ("_activity_bar", "_project_tree", "_tool_container", "_breadcrumb"):
            assert hasattr(win, attr), f"缺组件 {attr}"

        # workspace 加载成功
        assert win._workspace == workspace
        assert not win._project_tree.is_empty_state()

        # 默认选中 plot_curves（lazy 构造已完成）
        assert win._activity_bar.current() == "plot_curves"
        assert "plot_curves" in win._pages

        # 5 个工具名都注册了 factory
        for name in ("plot_curves", "leeb_hardness", "pdf_tools", "word2pdf", "settings"):
            assert name in win._page_factories

        # 切到 settings 触发 lazy 构造
        win._activity_bar.set_current("settings")
        assert "settings" in win._pages
        assert win._tool_container.currentIndex() == win._page_indices["settings"]
    finally:
        win.deleteLater()


def test_shell_construct_without_workspace_shows_empty_state(tmp_path, monkeypatch) -> None:
    """workspace=None → 项目树栏显示 empty state，shell 仍然能正常构造。"""
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    ws.clear_last_workspace()

    cfg = load_config()
    win = sw.ShellWindow(cfg, None)
    try:
        assert win._workspace is None
        assert win._project_tree.is_empty_state(), "无 workspace 时应显示 empty state"
        # 工具页仍然都在
        assert win._activity_bar.current() == "plot_curves"
    finally:
        win.deleteLater()


def test_load_workspace_updates_state(tmp_path, monkeypatch) -> None:
    """从 empty state 切到有 workspace → 项目树 + breadcrumb + QSettings 都应更新。"""
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    ws.clear_last_workspace()

    cfg = load_config()
    win = sw.ShellWindow(cfg, None)
    try:
        assert win._project_tree.is_empty_state()
        new_ws = tmp_path / "ws_new"
        create_standard_structure(new_ws)
        win._load_workspace(new_ws)
        assert win._workspace == new_ws
        assert not win._project_tree.is_empty_state()
        # QSettings 也应被写入
        assert ws.load_last_workspace() == new_ws
    finally:
        win.deleteLater()
