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
        # 核心组件就位
        for attr in ("_activity_bar", "_project_tree", "_tool_container", "_agent_panel", "_breadcrumb"):
            assert hasattr(win, attr), f"缺组件 {attr}"
        # 5 个工具页齐全
        for name in ("plot_curves", "leeb_hardness", "pdf_tools", "word2pdf", "settings"):
            assert name in win._pages

        # workspace 加载成功
        assert win._workspace == workspace
        assert not win._project_tree.is_empty_state()
        # AgentPanel 也接到了 workspace
        assert win._agent_panel.workspace() == workspace

        # 默认选中 plot_curves
        assert win._activity_bar.current() == "plot_curves"

        # 切到 settings
        win._activity_bar.set_current("settings")
        assert win._tool_container.currentWidget() is win._pages["settings"]
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
