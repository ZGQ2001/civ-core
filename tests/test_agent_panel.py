"""AgentPanel：占位空壳 smoke。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.ui.components.agent_panel import AgentPanel  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_construct_and_workspace_roundtrip(tmp_path: Path) -> None:
    _ensure_app()
    p = AgentPanel()
    assert p.workspace() is None
    ws = tmp_path / "ws"
    ws.mkdir()
    p.set_workspace(ws)
    assert p.workspace() == ws
