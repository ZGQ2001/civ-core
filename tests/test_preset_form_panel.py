"""PresetFormPanel 的轻量 smoke 测试。

为什么不用 pytest-qt
====================
项目当前 dependency-groups.dev 里没装 pytest-qt（与 project.optional-dependencies.dev
配置不一致，登记为后续修），所以这里直接用 QApplication 单例搭最小宿主，
跑纯逻辑断言（set_entry / current_data 往返、dirty 翻转、reset、read_only）。

不测的内容：
  - 渲染 / 视觉（控件位置 / 颜色 / 字体）
  - 鼠标键盘交互（让 Step 6 的手工验收覆盖）
  - JSON 文本框语法高亮等 Qt 行为
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# headless 模式：CI 没显示器也能跑
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from civ_core.infra_io.preset_manager import PresetEntry, PresetSource  # noqa: E402
from civ_core.ui.components.preset_form_panel import PresetFormPanel  # noqa: E402


# ──────────────────────────────────────────────────────────────────
# QApplication 进程级单例 fixture
# ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """整个测试进程共享一个 QApplication（Qt 不允许多个）。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


@pytest.fixture
def panel(qapp: QApplication) -> PresetFormPanel:
    """每个测试一个新面板，避免状态互染。"""
    p = PresetFormPanel()
    yield p
    p.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 测试数据
# ──────────────────────────────────────────────────────────────────
def _sample_data() -> dict[str, Any]:
    """与 presets/plot_curves/curve_presets.json 里"锚杆荷载-位移曲线"结构等价的样例。"""
    return {
        "id_column": "锚杆编号",
        "filename_template": "锚杆{id}_荷载位移曲线.png",
        "title_template": "锚杆{id}：荷载-位移曲线",
        "x_axis": {"label": "位移 (mm)", "range": None},
        "y_axis": {"label": "荷载 (KN)", "range": [0, 200, 20]},
        "curves": [
            {
                "name": "加载",
                "color": "#1F4FE0",
                "marker": "s",
                "linewidth": 2.0,
                "markersize": 7,
                "points": [],
            }
        ],
    }


def _sample_entry(source: PresetSource = PresetSource.SYSTEM) -> PresetEntry:
    return PresetEntry(name="锚杆荷载-位移曲线", data=_sample_data(), source=source)


# ──────────────────────────────────────────────────────────────────
# set_entry → current_data / current_name 往返
# ──────────────────────────────────────────────────────────────────
class TestRoundtrip:
    def test_set_entry_then_read_back(self, panel: PresetFormPanel) -> None:
        """set_entry 后 current_name + current_data 应该等价于原 entry.data。"""
        entry = _sample_entry()
        panel.set_entry(entry)

        assert panel.current_name() == "锚杆荷载-位移曲线"
        cur = panel.current_data()
        assert cur["id_column"] == "锚杆编号"
        assert cur["filename_template"] == "锚杆{id}_荷载位移曲线.png"
        assert cur["title_template"] == "锚杆{id}：荷载-位移曲线"
        assert cur["x_axis"]["label"] == "位移 (mm)"
        assert cur["x_axis"]["range"] is None  # 自动 = None
        assert cur["y_axis"]["label"] == "荷载 (KN)"
        assert cur["y_axis"]["range"] == [0.0, 200.0, 20.0]
        # curves 经 JSON round-trip，结构与原值一致
        assert cur["curves"] == _sample_data()["curves"]

    def test_set_entry_none_clears_form(self, panel: PresetFormPanel) -> None:
        """set_entry(None) → 表单字段清空（"+新建"场景）。"""
        panel.set_entry(_sample_entry())
        panel.set_entry(None)

        assert panel.current_name() == ""
        cur = panel.current_data()
        assert cur["id_column"] == ""
        assert cur["x_axis"]["label"] == ""
        assert cur["x_axis"]["range"] is None
        assert cur["y_axis"]["range"] is None
        assert cur["curves"] == []

    def test_range_with_only_two_values_padded_to_three(
        self, panel: PresetFormPanel
    ) -> None:
        """容错：JSON range 是 [min, max] 两元组时，step 用 0 填充。"""
        data = _sample_data()
        data["y_axis"]["range"] = [0, 100]
        entry = PresetEntry(name="t", data=data, source=PresetSource.USER)
        panel.set_entry(entry)

        cur = panel.current_data()
        assert cur["y_axis"]["range"] == [0.0, 100.0, 0.0]


# ──────────────────────────────────────────────────────────────────
# dirty 检测
# ──────────────────────────────────────────────────────────────────
class TestDirty:
    def test_initial_state_is_clean(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry())
        assert panel.is_dirty() is False

    def test_change_makes_dirty(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry())
        # 模拟用户改 id_column
        panel.id_column_edit.setText("新的列名")
        assert panel.is_dirty() is True

    def test_change_back_to_baseline_clears_dirty(
        self, panel: PresetFormPanel
    ) -> None:
        """改回原值 → dirty 自动恢复 False（用户敲完又改回去的常见路径）。"""
        panel.set_entry(_sample_entry())
        panel.id_column_edit.setText("临时改的")
        assert panel.is_dirty() is True
        panel.id_column_edit.setText("锚杆编号")  # 改回原值
        assert panel.is_dirty() is False

    def test_dirty_signal_emits_on_transitions(
        self, panel: PresetFormPanel
    ) -> None:
        """dirty_changed 只在状态翻转时 emit，不抖动。"""
        emitted: list[bool] = []
        panel.dirty_changed.connect(lambda v: emitted.append(v))
        panel.set_entry(_sample_entry())  # 初始 False，不应 emit（baseline 时已是 False）

        panel.id_column_edit.setText("a")  # → True
        panel.id_column_edit.setText("ab")  # 仍 True，不 emit
        panel.id_column_edit.setText("锚杆编号")  # → False
        assert emitted == [True, False]

    def test_range_change_makes_dirty(self, panel: PresetFormPanel) -> None:
        """改轴范围（取消"自动"）也算 dirty。"""
        panel.set_entry(_sample_entry())
        panel.x_range_row.auto_cb.setChecked(False)
        panel.x_range_row.min_spin.setValue(5.0)
        assert panel.is_dirty() is True


# ──────────────────────────────────────────────────────────────────
# reset / read_only
# ──────────────────────────────────────────────────────────────────
class TestResetAndReadOnly:
    def test_reset_to_baseline_restores_all_fields(
        self, panel: PresetFormPanel
    ) -> None:
        panel.set_entry(_sample_entry())
        panel.id_column_edit.setText("乱改")
        panel.x_range_row.auto_cb.setChecked(False)
        panel.x_range_row.min_spin.setValue(99.0)
        assert panel.is_dirty() is True

        panel.reset_to_baseline()

        assert panel.is_dirty() is False
        assert panel.current_data()["id_column"] == "锚杆编号"
        assert panel.current_data()["x_axis"]["range"] is None

    def test_set_read_only_disables_editing(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry(PresetSource.SYSTEM))
        panel.set_read_only(True)

        assert panel.name_edit.isReadOnly() is True
        assert panel.id_column_edit.isReadOnly() is True
        assert panel.curves_edit.isReadOnly() is True
        assert panel.x_range_row.auto_cb.isEnabled() is False
        assert panel.x_range_row.min_spin.isEnabled() is False

    def test_set_read_only_false_re_enables(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry(PresetSource.USER))
        panel.set_read_only(True)
        panel.set_read_only(False)

        assert panel.name_edit.isReadOnly() is False
        # range 启用与否要看 auto_cb：当前 entry.x_axis.range=None（auto 勾上）
        # → spin 仍禁用，但 auto_cb 应启用
        assert panel.x_range_row.auto_cb.isEnabled() is True


# ──────────────────────────────────────────────────────────────────
# curves JSON 文本解析容错
# ──────────────────────────────────────────────────────────────────
class TestCurvesParsing:
    def test_empty_text_returns_empty_list(self, panel: PresetFormPanel) -> None:
        panel.set_entry(None)
        panel.curves_edit.setPlainText("")
        assert panel.current_data()["curves"] == []

    def test_invalid_json_returns_error_marker(
        self, panel: PresetFormPanel
    ) -> None:
        """坏 JSON：current_data 返回带 _parse_error 标记的 list（不抛）。"""
        panel.set_entry(None)
        panel.curves_edit.setPlainText("[not valid")
        curves = panel.current_data()["curves"]
        assert len(curves) == 1
        assert "_parse_error" in curves[0]
        assert "_raw" in curves[0]

    def test_non_list_root_returns_error_marker(
        self, panel: PresetFormPanel
    ) -> None:
        panel.set_entry(None)
        panel.curves_edit.setPlainText('{"name": "x"}')
        curves = panel.current_data()["curves"]
        assert len(curves) == 1
        assert "_parse_error" in curves[0]
        assert "list" in curves[0]["_parse_error"]

    def test_current_curves_text_returns_raw(
        self, panel: PresetFormPanel
    ) -> None:
        panel.set_entry(None)
        panel.curves_edit.setPlainText('  [{"name": "a"}]  ')
        # 不去空白，原样返回，方便调用方拿到 JSON 错误位置
        assert panel.current_curves_text() == '  [{"name": "a"}]  '


# ──────────────────────────────────────────────────────────────────
# 底部按钮区三态可见性（Step 5）
# ──────────────────────────────────────────────────────────────────
class TestButtonVisibility:
    """系统/用户/新建三态的按钮显示规则。

    三态判定（与 _update_button_visibility 实现一致）：
      • read_only=True              → 系统：[复制为我的预设]
      • read_only=False, baseline="" → 新建：[保存为我的预设] [取消]
      • read_only=False, baseline 非空 → 用户：[保存修改] [重置]

    用 isVisibleTo(panel) 而非 isVisible() —— 后者要求 panel 自己也得显示，
    在 offscreen 单元测试里不成立；isVisibleTo 只看父子链条上的本地 visible 标志。
    """

    def test_system_state_shows_only_copy(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry(PresetSource.SYSTEM))
        panel.set_read_only(True)
        assert panel._copy_btn.isVisibleTo(panel) is True
        assert panel._save_btn.isVisibleTo(panel) is False
        assert panel._reset_btn.isVisibleTo(panel) is False
        assert panel._cancel_btn.isVisibleTo(panel) is False

    def test_user_state_shows_save_and_reset(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry(PresetSource.USER))
        panel.set_read_only(False)
        assert panel._copy_btn.isVisibleTo(panel) is False
        assert panel._save_btn.isVisibleTo(panel) is True
        assert panel._reset_btn.isVisibleTo(panel) is True
        assert panel._cancel_btn.isVisibleTo(panel) is False
        assert panel._save_btn.text() == "保存修改"

    def test_new_draft_state_shows_save_and_cancel(
        self, panel: PresetFormPanel
    ) -> None:
        panel.set_entry(None)
        panel.set_read_only(False)
        assert panel._copy_btn.isVisibleTo(panel) is False
        assert panel._save_btn.isVisibleTo(panel) is True
        assert panel._reset_btn.isVisibleTo(panel) is False
        assert panel._cancel_btn.isVisibleTo(panel) is True
        assert panel._save_btn.text() == "保存为我的预设"

    def test_save_button_disabled_when_clean(
        self, panel: PresetFormPanel
    ) -> None:
        """非 dirty 时保存按钮禁用（避免无意义的写盘）。"""
        panel.set_entry(_sample_entry(PresetSource.USER))
        panel.set_read_only(False)
        assert panel.is_dirty() is False
        assert panel._save_btn.isEnabled() is False

        panel.id_column_edit.setText("改了一下")
        assert panel.is_dirty() is True
        assert panel._save_btn.isEnabled() is True

    def test_save_button_emits_signal(self, panel: PresetFormPanel) -> None:
        emitted: list[None] = []
        panel.save_requested.connect(lambda: emitted.append(None))
        panel.set_entry(_sample_entry(PresetSource.USER))
        panel.set_read_only(False)
        panel.id_column_edit.setText("改了")  # 让按钮启用
        panel._save_btn.click()
        assert len(emitted) == 1

    def test_reset_button_emits_signal(self, panel: PresetFormPanel) -> None:
        emitted: list[None] = []
        panel.reset_requested.connect(lambda: emitted.append(None))
        panel.set_entry(_sample_entry(PresetSource.USER))
        panel.set_read_only(False)
        panel._reset_btn.click()
        assert len(emitted) == 1

    def test_copy_button_emits_signal(self, panel: PresetFormPanel) -> None:
        emitted: list[None] = []
        panel.copy_to_user_requested.connect(lambda: emitted.append(None))
        panel.set_entry(_sample_entry(PresetSource.SYSTEM))
        panel.set_read_only(True)
        panel._copy_btn.click()
        assert len(emitted) == 1

    def test_cancel_new_button_emits_signal(self, panel: PresetFormPanel) -> None:
        emitted: list[None] = []
        panel.cancel_new_requested.connect(lambda: emitted.append(None))
        panel.set_entry(None)
        panel.set_read_only(False)
        panel._cancel_btn.click()
        assert len(emitted) == 1


# ──────────────────────────────────────────────────────────────────
# baseline_name() 公共 API
# ──────────────────────────────────────────────────────────────────
class TestBaselineName:
    def test_returns_entry_name(self, panel: PresetFormPanel) -> None:
        panel.set_entry(_sample_entry())
        assert panel.baseline_name() == "锚杆荷载-位移曲线"

    def test_empty_when_new_draft(self, panel: PresetFormPanel) -> None:
        panel.set_entry(None)
        assert panel.baseline_name() == ""

    def test_unchanged_by_typing(self, panel: PresetFormPanel) -> None:
        """用户改 name 字段不应影响 baseline_name —— baseline 只在 set_entry 时刷新。"""
        panel.set_entry(_sample_entry())
        panel.name_edit.setText("用户乱改的")
        assert panel.baseline_name() == "锚杆荷载-位移曲线"
