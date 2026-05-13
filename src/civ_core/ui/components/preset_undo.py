"""预设字段撤销/重做控制器（P1.5-② 实装）。

为什么独立成模块
================
  • PresetAccordionPanel 已经 ~1200 行，再塞栈管理会更乱
  • 控制器与 panel 通过 `preset_changed` 信号 + `apply_preset_data` 方法解耦
  • 独立类便于单元测试 —— 用 Mock panel 就能跑，不依赖 Qt 事件循环

设计要点
========
  • 快照模式：每次 preset_changed → 整个 preset dict 进栈
    （不走 QUndoCommand 子类是因为字段实在太多，挨个写 setter 不值当）
  • 防抖：连续滑动 SpinBox 不应每次 valueChanged 都进栈；
    用 QTimer 在 _DEBOUNCE_MS 内合并成一条
  • 应用栈中数据时用 _suppress 标记防回路：apply 触发 preset_changed →
    被 _suppress 吞掉，不再回压栈
  • 截断未来分支：从历史中间又开始编辑 → 删掉 _cursor 之后的所有快照

栈深度上限 _MAX_DEPTH：50 步够日常用；超出后从底部 pop（保留最近 N 步）。
"""

from __future__ import annotations

import copy
from typing import Any, Protocol

from PySide6.QtCore import QObject, QTimer

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 防抖窗口：连续 preset_changed 在此时间窗内只压一条快照
_DEBOUNCE_MS = 300
# 栈深度上限（双向各算）
_MAX_DEPTH = 50


class _PresetPanelLike(Protocol):
    """控制器对 panel 的最小依赖（便于测试 mock）。"""

    def current_preset_data(self) -> dict[str, Any]: ...
    def apply_preset_data(self, data: dict[str, Any]) -> None: ...


class PresetUndoController(QObject):
    """监听 PresetAccordionPanel 字段变更 → 维护撤销/重做栈。

    使用方式（view 层）：
        ctrl = PresetUndoController(accordion_panel, parent=self)
        QShortcut(QKeySequence.StandardKey.Undo, self, ctrl.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, ctrl.redo)

    public API：
        undo() / redo()
        can_undo() / can_redo() : bool
        clear()                  : 全栈清空（切预设时调用 —— 不同预设的历史
                                   混在一起没意义）
    """

    def __init__(
        self,
        panel: _PresetPanelLike,
        parent: QObject | None = None,
        *,
        debounce_ms: int = _DEBOUNCE_MS,
        max_depth: int = _MAX_DEPTH,
    ) -> None:
        super().__init__(parent)
        self._panel = panel
        self._max_depth = max_depth
        self._suppress: bool = False
        # 栈：list[dict]，_cursor 指向当前显示在 UI 上的那条
        self._stack: list[dict[str, Any]] = []
        self._cursor: int = -1
        # 防抖 timer
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(debounce_ms)
        self._debounce_timer.timeout.connect(self._commit_pending)
        # 等待入栈的快照
        self._pending: dict[str, Any] | None = None

        # 启动时把当前状态作为基线
        self._push_initial()

    # ── 公共 API ─────────────────────────────────────────────────
    def can_undo(self) -> bool:
        return self._cursor > 0

    def can_redo(self) -> bool:
        return self._cursor < len(self._stack) - 1

    def undo(self) -> bool:
        """跳回上一个快照。已无更早历史 → 返回 False，不操作 UI。"""
        # 防抖中的待提交需要先落盘，否则用户撤销不到刚才的输入
        self._flush_pending()
        if not self.can_undo():
            return False
        self._cursor -= 1
        self._apply(self._stack[self._cursor])
        log.debug("undo → cursor=%d / depth=%d", self._cursor, len(self._stack))
        return True

    def redo(self) -> bool:
        """前进到下一个快照。无更新历史 → 返回 False。"""
        self._flush_pending()
        if not self.can_redo():
            return False
        self._cursor += 1
        self._apply(self._stack[self._cursor])
        log.debug("redo → cursor=%d / depth=%d", self._cursor, len(self._stack))
        return True

    def clear(self) -> None:
        """清空全栈，重新以当前 panel 状态为基线。

        切预设、加载新文件等"上下文整体改变"时调用 —— 旧上下文的历史无意义。
        """
        self._debounce_timer.stop()
        self._pending = None
        self._stack = [copy.deepcopy(self._panel.current_preset_data())]
        self._cursor = 0
        log.debug("undo stack cleared")

    def on_preset_changed(self, data: dict[str, Any]) -> None:
        """连接到 PresetAccordionPanel.preset_changed 的槽。

        恢复路径（_apply）触发的 preset_changed 被 _suppress 吞掉；
        其他都进入防抖 → 入栈。
        """
        if self._suppress:
            return
        # 取 panel 当前真实数据更稳（信号参数有时被 emit 者拷贝过早）
        # 但 data 已经是当前状态，直接 deepcopy 即可
        self._pending = copy.deepcopy(data)
        self._debounce_timer.start()

    # ── 内部 ──────────────────────────────────────────────────────
    def _push_initial(self) -> None:
        snap = copy.deepcopy(self._panel.current_preset_data())
        self._stack = [snap]
        self._cursor = 0

    def _commit_pending(self) -> None:
        if self._pending is None:
            return
        snap = self._pending
        self._pending = None
        # 与当前快照相同 → 不入栈（防止重复 commit 相同状态）
        if self._stack and self._stack[self._cursor] == snap:
            return
        # 截断未来：从历史中间又开始编辑 → 删掉之后的所有快照
        self._stack = self._stack[: self._cursor + 1]
        self._stack.append(snap)
        # 超深度从底部丢
        if len(self._stack) > self._max_depth:
            drop = len(self._stack) - self._max_depth
            self._stack = self._stack[drop:]
            self._cursor = len(self._stack) - 1
        else:
            self._cursor += 1
        log.debug(
            "undo push → cursor=%d / depth=%d", self._cursor, len(self._stack)
        )

    def _flush_pending(self) -> None:
        """undo/redo 前确保 pending 已经入栈，避免"按了 Ctrl+Z 跳过了刚改的"。"""
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
            self._commit_pending()

    def _apply(self, snap: dict[str, Any]) -> None:
        """把 snap 写回 panel；走 _suppress 防回路。"""
        self._suppress = True
        try:
            self._panel.apply_preset_data(copy.deepcopy(snap))
        finally:
            self._suppress = False
