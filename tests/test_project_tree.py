"""ProjectTree：set_root + .civ-core 隐藏 + 非目录拒绝。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.infra_io.workspace_scaffold import create_standard_structure  # noqa: E402
from civ_core.ui.components.project_tree import ProjectTree  # noqa: E402


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_construct() -> None:
    _ensure_app()
    t = ProjectTree()
    assert t.root() is None


def test_set_root_emits(qtbot, tmp_path: Path) -> None:
    _ensure_app()
    root = tmp_path / "ws"
    create_standard_structure(root)
    t = ProjectTree()
    qtbot.addWidget(t)
    with qtbot.waitSignal(t.workspace_changed, timeout=500) as sig:
        t.set_root(root)
    assert sig.args == [root]
    assert t.root() == root


def test_set_root_rejects_non_directory(tmp_path: Path) -> None:
    _ensure_app()
    f = tmp_path / "file.txt"
    f.write_text("x")
    t = ProjectTree()
    with pytest.raises(ValueError):
        t.set_root(f)


def test_civ_core_hidden_after_load(qtbot, tmp_path: Path) -> None:
    """.civ-core 目录应被树视图隐藏（即使 model 里看得到）。"""
    _ensure_app()
    root = tmp_path / "ws"
    create_standard_structure(root)
    t = ProjectTree()
    qtbot.addWidget(t)
    t.set_root(root)

    # 等 QFileSystemModel 异步扫描完成；directoryLoaded 信号触发后 .civ-core 应该被隐藏
    def _scan_done() -> bool:
        idx = t._model.index(str(root))
        for row in range(t._model.rowCount(idx)):
            if t._model.fileName(t._model.index(row, 0, idx)) == ".civ-core":
                # 找到了 .civ-core 行 → 验证它被隐藏
                return t._tree.isRowHidden(row, idx)
        # 还没扫到 .civ-core，继续等
        return False

    qtbot.waitUntil(_scan_done, timeout=3000)
