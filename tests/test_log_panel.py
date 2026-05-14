"""LogPanel 单元测试（使用 pytest-qt 的 qtbot fixture）。

把 pytest-qt 装进 dev 依赖后第一个用上 qtbot 的测试 —— 让它顺便起到
"基础设施验证"作用：确认 qtbot 能在本项目正常工作。

不测的内容：
  • HTML 渲染像素颜色（依赖 Qt 内部）
  • 滚动条位置（依赖 widget 实际尺寸，offscreen 不准）
  • ComboBox 视觉样式（qfluentwidgets 内部）
"""

from __future__ import annotations

import logging
import os

import pytest

# pytest-qt 不显式 import；qtbot fixture 由 plugin 自动注入
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from civ_core.ui.components.log_panel import LogPanel  # noqa: E402


def _make_record(
    name: str = "civ_core.foo",
    level: int = logging.INFO,
    msg: str = "hello",
) -> logging.LogRecord:
    """造一条 LogRecord 用于测试 on_record。"""
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


@pytest.fixture
def panel(qtbot) -> LogPanel:
    p = LogPanel()
    qtbot.addWidget(p)  # 让 qtbot 在测试结束时自动 cleanup
    return p


# ──────────────────────────────────────────────────────────────────
# 初始状态
# ──────────────────────────────────────────────────────────────────
class TestInitialState:
    def test_starts_collapsed(self, panel: LogPanel) -> None:
        """默认折叠 —— 避免开屏一堆日志干扰主操作区。"""
        assert panel.is_collapsed() is True

    def test_text_area_hidden_when_collapsed(self, panel: LogPanel) -> None:
        assert panel._text.isVisibleTo(panel) is False

    def test_toggle_button_shows_collapsed_arrow(self, panel: LogPanel) -> None:
        assert panel._toggle_btn.text() == "▶"

    def test_text_area_empty(self, panel: LogPanel) -> None:
        assert panel._text.toPlainText() == ""


# ──────────────────────────────────────────────────────────────────
# 折叠 / 展开
# ──────────────────────────────────────────────────────────────────
class TestCollapse:
    def test_set_collapsed_false_shows_text(self, panel: LogPanel) -> None:
        panel.set_collapsed(False)
        assert panel._text.isVisibleTo(panel) is True
        assert panel._toggle_btn.text() == "▼"

    def test_set_collapsed_true_hides_text(self, panel: LogPanel) -> None:
        panel.set_collapsed(False)
        panel.set_collapsed(True)
        assert panel._text.isVisibleTo(panel) is False
        assert panel._toggle_btn.text() == "▶"

    def test_collapse_signal_emits_on_change(self, panel: LogPanel, qtbot) -> None:
        with qtbot.waitSignal(panel.collapse_changed, timeout=1000) as blocker:
            panel.set_collapsed(False)
        assert blocker.args == [False]

    def test_collapse_signal_skips_when_already_in_state(self, panel: LogPanel, qtbot) -> None:
        """重复 set_collapsed 同状态 → 不该 emit 信号（防抖动）。"""
        emitted: list[bool] = []
        panel.collapse_changed.connect(lambda v: emitted.append(v))
        # 已经是 collapsed=True，再设一次 True
        panel.set_collapsed(True)
        assert emitted == []

    def test_toggle_button_click_flips_state(self, panel: LogPanel, qtbot) -> None:
        assert panel.is_collapsed() is True
        qtbot.mouseClick(panel._toggle_btn, qtbot_mouse_button())
        assert panel.is_collapsed() is False
        qtbot.mouseClick(panel._toggle_btn, qtbot_mouse_button())
        assert panel.is_collapsed() is True


def qtbot_mouse_button():
    """LeftButton 别名 —— 让 mouseClick 调用更简洁。"""
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton


# ──────────────────────────────────────────────────────────────────
# on_record：filter + 格式 + 颜色 inline
# ──────────────────────────────────────────────────────────────────
class TestOnRecord:
    def test_info_record_appears(self, panel: LogPanel) -> None:
        panel.on_record(_make_record(level=logging.INFO, msg="hello"))
        text = panel._text.toPlainText()
        assert "hello" in text
        assert "INFO" in text

    def test_debug_filtered_out_by_default(self, panel: LogPanel) -> None:
        """默认 filter = INFO，DEBUG 不显示。"""
        panel.on_record(_make_record(level=logging.DEBUG, msg="debug noise"))
        assert "debug noise" not in panel._text.toPlainText()

    def test_logger_name_shortened_to_last_segment(self, panel: LogPanel) -> None:
        panel.on_record(_make_record(name="civ_core.ui.preset_list", msg="picked"))
        text = panel._text.toPlainText()
        # 只显示最后一级 logger 名
        assert "preset_list" in text
        # 不应出现完整路径
        assert "civ_core.ui." not in text

    def test_warning_message_present(self, panel: LogPanel) -> None:
        panel.on_record(_make_record(level=logging.WARNING, msg="warn!"))
        text = panel._text.toPlainText()
        assert "WARN" in text
        assert "warn!" in text

    def test_error_message_present(self, panel: LogPanel) -> None:
        panel.on_record(_make_record(level=logging.ERROR, msg="boom"))
        assert "ERROR" in panel._text.toPlainText()

    def test_html_special_chars_escaped(self, panel: LogPanel) -> None:
        """msg 含 < > & 等 HTML 特殊字符 → 转义后正确显示。"""
        panel.on_record(_make_record(msg="a<b & c>d"))
        # toPlainText 应该看到原文（QPlainTextEdit 的 toPlainText 已自动反转义）
        assert "a<b & c>d" in panel._text.toPlainText()

    def test_message_args_applied(self, panel: LogPanel) -> None:
        """LogRecord 自带 args → getMessage() 后填入。"""
        rec = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="value=%d count=%s",
            args=(42, "abc"),
            exc_info=None,
        )
        panel.on_record(rec)
        assert "value=42 count=abc" in panel._text.toPlainText()


# ──────────────────────────────────────────────────────────────────
# 级别过滤：set_level_filter / ComboBox 联动
# ──────────────────────────────────────────────────────────────────
class TestLevelFilter:
    def test_set_level_filter_to_warning(self, panel: LogPanel) -> None:
        panel.set_level_filter(logging.WARNING)
        # INFO 现在被过滤
        panel.on_record(_make_record(level=logging.INFO, msg="silent"))
        assert "silent" not in panel._text.toPlainText()
        # WARN 仍显示
        panel.on_record(_make_record(level=logging.WARNING, msg="loud"))
        assert "loud" in panel._text.toPlainText()

    def test_set_level_filter_to_debug_shows_all(self, panel: LogPanel) -> None:
        panel.set_level_filter(logging.DEBUG)
        panel.on_record(_make_record(level=logging.DEBUG, msg="trace"))
        assert "trace" in panel._text.toPlainText()

    def test_combo_change_updates_filter(self, panel: LogPanel) -> None:
        """改 ComboBox 选项 → 后续 on_record 按新 level 过滤。"""
        # 选"全部"（index 0 = DEBUG）
        panel._level_combo.setCurrentIndex(0)
        panel.on_record(_make_record(level=logging.DEBUG, msg="now visible"))
        assert "now visible" in panel._text.toPlainText()


# ──────────────────────────────────────────────────────────────────
# clear
# ──────────────────────────────────────────────────────────────────
class TestClear:
    def test_clear_empties_display(self, panel: LogPanel) -> None:
        panel.on_record(_make_record(msg="will be cleared"))
        assert panel._text.toPlainText() != ""
        panel.clear()
        assert panel._text.toPlainText() == ""

    def test_clear_button_emits_to_clear(self, panel: LogPanel, qtbot) -> None:
        panel.on_record(_make_record(msg="bye"))
        qtbot.mouseClick(panel._clear_btn, qtbot_mouse_button())
        assert panel._text.toPlainText() == ""


# ──────────────────────────────────────────────────────────────────
# 自动滚动 CheckBox 联动
# ──────────────────────────────────────────────────────────────────
class TestAutoScroll:
    def test_uncheck_disables_auto_scroll(self, panel: LogPanel) -> None:
        panel._auto_scroll_cb.setChecked(False)
        assert panel._auto_scroll is False

    def test_check_enables_auto_scroll(self, panel: LogPanel) -> None:
        panel._auto_scroll_cb.setChecked(False)
        panel._auto_scroll_cb.setChecked(True)
        assert panel._auto_scroll is True


# ──────────────────────────────────────────────────────────────────
# 容量上限：超出 _MAX_BLOCKS 自动丢老
# ──────────────────────────────────────────────────────────────────
class TestCapacity:
    def test_exceeds_max_blocks_drops_old(self, panel: LogPanel) -> None:
        """灌入超过 _MAX_BLOCKS 条 → 最早的应被自动丢弃。

        用 split lines + 行尾精确匹配判断，避免 "msg-4" 是 "msg-40" 子串
        这种假阳性。QPlainTextEdit.setMaximumBlockCount 保证 block 不超出，
        所以行数应等于 _MAX_BLOCKS。
        """
        from civ_core.ui.components.log_panel import _MAX_BLOCKS

        # 灌 _MAX_BLOCKS + 5 条，每条带唯一标识
        for i in range(_MAX_BLOCKS + 5):
            panel.on_record(_make_record(msg=f"msg-{i}"))

        # 取所有"消息后缀"：行格式末尾是 "— msg-N"
        lines = panel._text.toPlainText().splitlines()
        msg_ids = {line.rsplit("— ", 1)[1] for line in lines if "— msg-" in line}

        # block count 不超过 _MAX_BLOCKS（Qt 自动丢老）
        assert len(lines) <= _MAX_BLOCKS

        # 最老的若干条应该已丢弃
        assert "msg-0" not in msg_ids
        assert "msg-4" not in msg_ids
        # 最新的还在
        assert f"msg-{_MAX_BLOCKS + 4}" in msg_ids
