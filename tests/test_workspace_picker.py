"""WorkspacePickerDialog：构造 + selected_path 钩子（不触发文件对话框 UI）。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from civ_core.ui.dialogs.workspace_picker import WorkspacePickerDialog  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_construct_initial_state() -> None:
    _ensure_app()
    d = WorkspacePickerDialog()
    assert d.selected_path() is None
    assert d.isModal()


def test_set_selected_and_accept(tmp_path: Path) -> None:
    """直接走 set_selected_path + accept，绕过文件对话框（CI/headless 友好）。"""
    _ensure_app()
    d = WorkspacePickerDialog()
    p = tmp_path / "ws"
    p.mkdir()
    d.set_selected_path(p)
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted
    assert d.selected_path() == p


def test_reject_keeps_selected_none() -> None:
    _ensure_app()
    d = WorkspacePickerDialog()
    d.reject()
    assert d.result() == QDialog.DialogCode.Rejected
    assert d.selected_path() is None
