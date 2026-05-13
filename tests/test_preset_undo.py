"""PresetUndoController 单元测试（P1.5-②）。

测试目标：
  • 基线快照：构造时栈深 1，cursor=0，can_undo/can_redo 均 False
  • 防抖：连续 on_preset_changed 在 _DEBOUNCE_MS 内只入一条
  • undo/redo：cursor 前后移动 + apply_preset_data 被调用
  • 截断未来：历史中间又改 → 删掉之后所有快照
  • 栈深度上限：超限从底部 pop
  • _suppress 防回路：apply 时 preset_changed 被忽略
  • clear()：重置到当前 panel 状态

不依赖 PresetAccordionPanel 真实实现 —— 用 _MockPanel。
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


class _MockPanel:
    """模拟 PresetAccordionPanel 的最小子集。current_preset_data 返回
    self._state；apply_preset_data 覆盖 self._state 并记录调用。"""

    def __init__(self, initial: dict[str, Any]) -> None:
        self._state: dict[str, Any] = dict(initial)
        self.apply_calls: list[dict[str, Any]] = []

    def current_preset_data(self) -> dict[str, Any]:
        return dict(self._state)

    def apply_preset_data(self, data: dict[str, Any]) -> None:
        self._state = dict(data)
        self.apply_calls.append(dict(data))


# ──────────────────────────────────────────────────────────────────
# 基线
# ──────────────────────────────────────────────────────────────────
class TestBaseline:
    def test_initial_stack(self, qapp: QApplication) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 1})
        ctrl = PresetUndoController(panel)
        try:
            assert ctrl.can_undo() is False
            assert ctrl.can_redo() is False
            assert len(ctrl._stack) == 1
            assert ctrl._cursor == 0
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 防抖：连续 on_preset_changed 合并成一条
# ──────────────────────────────────────────────────────────────────
class TestDebounce:
    def test_three_changes_in_window_push_one(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=100)
        try:
            ctrl.on_preset_changed({"k": 1})
            ctrl.on_preset_changed({"k": 2})
            ctrl.on_preset_changed({"k": 3})
            qtbot.wait(200)
            # 基线 + 1 条新快照
            assert len(ctrl._stack) == 2
            assert ctrl._stack[-1] == {"k": 3}
            assert ctrl._cursor == 1
        finally:
            ctrl.deleteLater()

    def test_two_windows_push_two(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=80)
        try:
            ctrl.on_preset_changed({"k": 1})
            qtbot.wait(150)
            ctrl.on_preset_changed({"k": 2})
            qtbot.wait(150)
            assert len(ctrl._stack) == 3
            assert ctrl._stack[-1] == {"k": 2}
        finally:
            ctrl.deleteLater()

    def test_no_op_change_skipped(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        """value 没变 → 不入栈。"""
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=80)
        try:
            ctrl.on_preset_changed({"k": 0})  # 与基线相同
            qtbot.wait(150)
            assert len(ctrl._stack) == 1
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# undo / redo
# ──────────────────────────────────────────────────────────────────
class TestUndoRedo:
    def test_undo_redo_round_trip(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=50)
        try:
            ctrl.on_preset_changed({"k": 1})
            qtbot.wait(100)
            ctrl.on_preset_changed({"k": 2})
            qtbot.wait(100)
            # stack = [{k:0}, {k:1}, {k:2}], cursor=2
            assert ctrl.can_undo()
            assert not ctrl.can_redo()

            assert ctrl.undo() is True
            assert panel.current_preset_data() == {"k": 1}
            assert ctrl.can_undo()
            assert ctrl.can_redo()

            assert ctrl.undo() is True
            assert panel.current_preset_data() == {"k": 0}
            assert not ctrl.can_undo()
            assert ctrl.can_redo()

            assert ctrl.undo() is False  # 到底了

            assert ctrl.redo() is True
            assert panel.current_preset_data() == {"k": 1}
            assert ctrl.redo() is True
            assert panel.current_preset_data() == {"k": 2}
            assert ctrl.redo() is False  # 顶了
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 截断未来分支
# ──────────────────────────────────────────────────────────────────
class TestBranchTruncation:
    def test_edit_in_middle_truncates_future(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=50)
        try:
            ctrl.on_preset_changed({"k": 1})
            qtbot.wait(100)
            ctrl.on_preset_changed({"k": 2})
            qtbot.wait(100)
            ctrl.undo()  # 回到 {k:1}
            assert ctrl.can_redo()

            # 从这里改 → 截断 {k:2}
            ctrl.on_preset_changed({"k": 99})
            qtbot.wait(100)
            assert not ctrl.can_redo()
            assert ctrl._stack[-1] == {"k": 99}
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 栈深度上限
# ──────────────────────────────────────────────────────────────────
class TestStackDepthLimit:
    def test_pops_from_bottom_when_exceeded(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=20, max_depth=3)
        try:
            for i in range(1, 6):  # push {k:1}..{k:5}
                ctrl.on_preset_changed({"k": i})
                qtbot.wait(50)
            # 上限 3 → 最近 3 条
            assert len(ctrl._stack) == 3
            assert ctrl._stack[0] == {"k": 3}
            assert ctrl._stack[-1] == {"k": 5}
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# _suppress 防回路
# ──────────────────────────────────────────────────────────────────
class TestSuppress:
    def test_apply_does_not_recurse(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        """模拟：apply 触发的 on_preset_changed 不应再入栈。"""
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=30)
        try:
            ctrl.on_preset_changed({"k": 1})
            qtbot.wait(80)
            depth_before = len(ctrl._stack)

            # 模拟 apply 重入（真实场景：apply 触发 valueChanged）
            ctrl._suppress = True
            ctrl.on_preset_changed({"k": 999})
            ctrl._suppress = False
            qtbot.wait(80)

            assert len(ctrl._stack) == depth_before
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# undo 前 flush pending
# ──────────────────────────────────────────────────────────────────
class TestFlushPendingBeforeUndo:
    def test_undo_commits_in_flight_change(
        self, qapp: QApplication
    ) -> None:
        """正在防抖中的修改也算"已发生"，undo 应能跳过它回到上一个稳定点。

        语义：
          基线 → 改 A（防抖中没 commit）→ 立刻按 Ctrl+Z
          预期：A 先 commit 入栈，然后 undo 回到基线
        """
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=500)
        try:
            ctrl.on_preset_changed({"k": 1})  # 防抖中
            # 立刻 undo（不等防抖）
            ctrl.undo()
            # 期望：A 入栈（stack = [{k:0}, {k:1}]）→ undo 把 cursor 退回 0
            assert ctrl._cursor == 0
            assert panel.current_preset_data() == {"k": 0}
            assert len(ctrl._stack) == 2
        finally:
            ctrl.deleteLater()


# ──────────────────────────────────────────────────────────────────
# clear
# ──────────────────────────────────────────────────────────────────
class TestClear:
    def test_clear_resets_to_current(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.preset_undo import PresetUndoController

        panel = _MockPanel({"k": 0})
        ctrl = PresetUndoController(panel, debounce_ms=30)
        try:
            ctrl.on_preset_changed({"k": 5})
            qtbot.wait(80)
            ctrl.on_preset_changed({"k": 10})
            qtbot.wait(80)
            assert len(ctrl._stack) == 3

            # 改 panel 状态后 clear，新基线应当是这个新状态
            panel._state = {"k": 999}
            ctrl.clear()
            assert len(ctrl._stack) == 1
            assert ctrl._cursor == 0
            assert ctrl._stack[0] == {"k": 999}
            assert not ctrl.can_undo()
            assert not ctrl.can_redo()
        finally:
            ctrl.deleteLater()
