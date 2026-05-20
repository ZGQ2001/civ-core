"""ShellWindow + resolve_workspace_or_prompt：构造 + 启动门槛 + 工具切换。"""

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
    """让 workspace_settings 的 QSettings 走临时目录，避免污染用户家目录。"""
    ini = tmp_path / "ws.ini"
    monkeypatch.setattr(
        ws,
        "_make_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def test_resolve_uses_cached_when_valid(tmp_path, monkeypatch) -> None:
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)

    workspace = tmp_path / "cached_ws"
    create_standard_structure(workspace)
    ws.save_last_workspace(workspace)

    got = sw.resolve_workspace_or_prompt()
    assert got == workspace


def test_resolve_returns_none_when_cancelled(tmp_path, monkeypatch) -> None:
    """缓存无效 → 弹对话框；monkeypatch 对话框直接 reject → 返回 None。"""
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)
    # 无缓存
    ws.clear_last_workspace()

    # monkeypatch 对话框：构造完直接 reject
    from civ_core.ui.dialogs.workspace_picker import WorkspacePickerDialog

    class _CancelDialog(WorkspacePickerDialog):
        def exec(self) -> int:  # type: ignore[override]
            return WorkspacePickerDialog.DialogCode.Rejected

    monkeypatch.setattr(sw, "WorkspacePickerDialog", _CancelDialog)
    assert sw.resolve_workspace_or_prompt() is None


def test_shell_construct(tmp_path, monkeypatch) -> None:
    """ShellWindow 能在一个合法 workspace 上构造起来，工具页全部就位。"""
    _ensure_app()
    _isolate_settings(tmp_path, monkeypatch)

    workspace = tmp_path / "ws_shell"
    create_standard_structure(workspace)

    cfg = load_config()
    win = sw.ShellWindow(cfg, workspace)
    try:
        # 各核心组件就位
        assert hasattr(win, "_activity_bar")
        assert hasattr(win, "_project_tree")
        assert hasattr(win, "_tool_container")
        assert hasattr(win, "_agent_panel")
        assert hasattr(win, "_breadcrumb")

        # 工具页齐全
        for name in ("plot_curves", "leeb_hardness", "pdf_tools", "word2pdf", "settings"):
            assert name in win._pages

        # 默认 activity_bar 选中 plot_curves
        assert win._activity_bar.current() == "plot_curves"

        # 切到 settings 后 stacked currentWidget 应同步
        win._activity_bar.set_current("settings")
        assert win._tool_container.currentWidget() is win._pages["settings"]

        # 面包屑包含工作区名和工具名
        win._breadcrumb._crumb.text()  # 不为空足矣
    finally:
        win.deleteLater()
