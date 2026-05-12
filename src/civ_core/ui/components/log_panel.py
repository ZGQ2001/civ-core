"""日志显示面板（接 QtLogBridge）。

布局
====
  ┌──────────────────────────────────────────────┐
  │ ▼ 日志   [级别 ▾]  [✓自动滚动]  [清空]        │  ← 工具栏（始终可见）
  ├──────────────────────────────────────────────┤
  │ HH:MM:SS  [INFO]  preset_list — 已选预设：…  │  ← 折叠时隐藏
  │ HH:MM:SS  [WARN]  plot_curves — 失败 1 条…  │
  │ ...                                          │
  └──────────────────────────────────────────────┘

设计取舍
========
  • 用 QPlainTextEdit 而不是 QListWidget —— 文本视图原生支持等宽字体 + 多行自动换行，
    比 QListWidget 处理性能好（QPlainTextEdit 内部用 line-based 模型）
  • setMaximumBlockCount(1000) 让超出自动丢老条目，无需自己管内存
  • 颜色用 appendHtml 的 inline <span style="color:..."> —— 简单可靠，比维护
    setExtraSelections 状态更省心
  • 折叠不重排上层 layout：直接 setVisible(False) 让 QSplitter / QVBoxLayout
    自然把空间还给上面的内容；面板自身高度会塌到只剩工具栏
  • 自动滚动判定：用户拉到底部时 emit 才滚；用户向上看历史时不打扰
  • 级别过滤：改 filter 后的新条目按新规则；旧条目不重读历史（要看历史去 logs/app.log）

接入方式（在 view 里）：
  bridge = get_qt_bridge()
  if bridge:
      bridge.record_emitted.connect(self.log_panel.on_record)
"""

from __future__ import annotations

import html
import logging
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    PushButton,
    TransparentToolButton,
)

# 日志面板里 QPlainTextEdit 最多保留多少条 —— 超出自动丢老
# 1000 条对人眼足够回看；占内存几百 KB 量级
_MAX_BLOCKS = 1000

# 级别 → 颜色（inline CSS color 值）
# 选色逻辑：
#   DEBUG  灰  —— 跑不出图也想看的细节
#   INFO   黑  —— 默认正常输出
#   WARN   橙黄 —— 需要注意但没崩
#   ERROR  红  —— 真出错了
#   CRIT   白底红 —— 极端情况（代码里很少用）
_LEVEL_STYLE: dict[int, str] = {
    logging.DEBUG: "color:#888;",
    logging.INFO: "color:#222;",
    logging.WARNING: "color:#d57500;font-weight:600;",
    logging.ERROR: "color:#c33;font-weight:600;",
    logging.CRITICAL: "background:#c33;color:#fff;font-weight:700;",
}
_LEVEL_TEXT: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}

# ComboBox 里给用户选的过滤级别（按 levelno 升序）
_FILTER_OPTIONS: list[tuple[str, int]] = [
    ("全部", logging.DEBUG),
    ("INFO 以上", logging.INFO),
    ("WARN 以上", logging.WARNING),
    ("ERROR 以上", logging.ERROR),
]
_DEFAULT_FILTER = logging.INFO  # 默认隐藏 DEBUG 噪音


class LogPanel(QWidget):
    """显示运行时日志的折叠面板。

    Signals:
      collapse_changed(bool) —— 折叠态翻转时 emit。view 可据此把
                                splitter 里日志区的高度记住/恢复（本轮暂不做）

    Public API:
      • on_record(record)         logging.LogRecord 的接收槽
      • set_collapsed(bool)       折叠 / 展开
      • is_collapsed() -> bool
      • clear()                   清空当前显示
      • set_level_filter(int)     设置最低显示级别（≥ 此 levelno 才显示）
    """

    collapse_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logPanel")

        self._collapsed = True  # 默认折叠：避免开屏一堆日志干扰
        self._level_filter = _DEFAULT_FILTER
        self._auto_scroll = True

        self._build_ui()
        self._wire_signals()
        self._apply_collapsed_state()

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 顶部工具栏（始终可见）──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        toolbar.setSpacing(8)

        # 折叠切换：用文字符号 ▶/▼ 直接显示状态，免依赖 FluentIcon 的特定 chevron 图标
        self._toggle_btn = TransparentToolButton(self)
        self._toggle_btn.setText("▶")
        self._toggle_btn.setToolTip("展开 / 折叠日志面板")
        toolbar.addWidget(self._toggle_btn)

        toolbar.addWidget(BodyLabel("日志", self))

        toolbar.addSpacing(16)

        toolbar.addWidget(BodyLabel("级别：", self))
        self._level_combo = ComboBox(self)
        for label, _ in _FILTER_OPTIONS:
            self._level_combo.addItem(label)
        # 默认选中 INFO 以上 —— 与 _DEFAULT_FILTER 对应
        for i, (_, level) in enumerate(_FILTER_OPTIONS):
            if level == _DEFAULT_FILTER:
                self._level_combo.setCurrentIndex(i)
                break
        self._level_combo.setMinimumWidth(110)
        toolbar.addWidget(self._level_combo)

        self._auto_scroll_cb = CheckBox("自动滚动", self)
        self._auto_scroll_cb.setChecked(True)
        toolbar.addWidget(self._auto_scroll_cb)

        toolbar.addStretch(1)

        self._clear_btn = PushButton("清空", self)
        toolbar.addWidget(self._clear_btn)

        outer.addLayout(toolbar)

        # ── 主体：日志显示区 ──
        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        # 关掉 wrap 让长行水平滚动而不是换行；日志更容易看
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMaximumBlockCount(_MAX_BLOCKS)
        # 等宽字体让时间戳 / level 标签对齐美观
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(9)
        self._text.setFont(font)
        # 简洁视觉：去边框去 margin，让 BottomTabPanel 提供整体边界
        self._text.setStyleSheet(
            "QPlainTextEdit { "
            "  background: #fafafa; "
            "  border: none; "
            "} "
        )
        self._text.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        outer.addWidget(self._text, 1)

    def _wire_signals(self) -> None:
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        self._level_combo.currentIndexChanged.connect(self._on_level_changed)
        self._auto_scroll_cb.toggled.connect(self._on_auto_scroll_toggled)
        self._clear_btn.clicked.connect(self.clear)

    # ── 公共 API ──────────────────────────────────────────────────
    def on_record(self, record: logging.LogRecord) -> None:
        """连接到 QtLogBridge.record_emitted。线程安全（Qt 队列连接）。"""
        if record.levelno < self._level_filter:
            return

        # 时间：HH:MM:SS（只到秒，避免一行太长；要毫秒去 logs/app.log）
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # logger 名简化：保留最后一级（civ_core.foo.bar → bar）
        # 顶层 root logger 的 name == "root"，保持原样
        logger_short = record.name.rsplit(".", 1)[-1]

        level_text = _LEVEL_TEXT.get(record.levelno, str(record.levelno))
        style = _LEVEL_STYLE.get(record.levelno, "color:#222;")

        # message 经 getMessage 应用 args；HTML 转义避免 <、& 这种字符破坏行
        msg = html.escape(record.getMessage())

        line = (
            f'<span style="{style}">'
            f"{ts}  [{level_text:<5}]  {html.escape(logger_short)} — {msg}"
            f"</span>"
        )
        self._text.appendHtml(line)

        # 自动滚动到最底（仅当用户没拉历史时；通过滚动条位置判断）
        if self._auto_scroll:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_collapsed_state()
        self.collapse_changed.emit(collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def clear(self) -> None:
        """清空日志显示。"""
        self._text.clear()

    def set_level_filter(self, level: int) -> None:
        """改最低显示级别。新条目按新规则；不复读历史。"""
        self._level_filter = level
        # 同步到 ComboBox 显示
        for i, (_, lv) in enumerate(_FILTER_OPTIONS):
            if lv == level:
                self._level_combo.blockSignals(True)
                self._level_combo.setCurrentIndex(i)
                self._level_combo.blockSignals(False)
                break

    # ── 内部 ──────────────────────────────────────────────────────
    def _apply_collapsed_state(self) -> None:
        """根据 self._collapsed 切 widget 可见性 + 切换按钮文字。"""
        self._text.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")
        # 折叠时面板高度只剩工具栏；展开时父布局会按 stretch 给空间

    def _on_toggle_clicked(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _on_level_changed(self, idx: int) -> None:
        if 0 <= idx < len(_FILTER_OPTIONS):
            _, level = _FILTER_OPTIONS[idx]
            self._level_filter = level

    def _on_auto_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = checked
