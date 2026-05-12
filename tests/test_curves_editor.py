"""CurvesEditor（L-3a）单元测试。

覆盖：
  • set_curves / curves() 深拷贝往返：外部 mutate 不影响编辑器，反之亦然
  • 增/复制/上移/下移：列表状态正确
  • 删除：MessageBox 二次确认（用 monkeypatch 直接放行/拒绝）
  • 点序列：fixed_axis / fixed_value / var_column 编辑回写
  • set_excel_headers：var_column cellWidget 从 LineEdit 升级为 ComboBox
  • changed 信号：编辑后发出 / 程序性 _render_form 不误发

不测的内容：
  • QColorDialog 弹窗（依赖系统 native 控件）
  • marker ComboBox 全部 8 个选项的逐个切换（信号机制同 linewidth）
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


def _sample_curves() -> list[dict[str, Any]]:
    return [
        {
            "name": "加载",
            "color": "#1F4FE0",
            "marker": "s",
            "linewidth": 2.0,
            "markersize": 7.0,
            "points": [
                {"fixed_axis": "y", "fixed_value": 60.0, "var_column": "60kN 位移"},
                {"fixed_axis": "y", "fixed_value": 90.0, "var_column": "90kN 位移"},
            ],
        },
        {
            "name": "卸载",
            "color": "#E03A3A",
            "marker": "o",
            "linewidth": 1.5,
            "markersize": 6.0,
            "points": [],
        },
    ]


# ──────────────────────────────────────────────────────────────────
# 深拷贝边界：外部 mutate 不污染编辑器
# ──────────────────────────────────────────────────────────────────
class TestRoundtripIsolation:
    def test_set_curves_makes_own_copy(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            src = _sample_curves()
            ed.set_curves(src)
            # 外部 mutate
            src[0]["name"] = "外部改了"
            src[0]["points"][0]["fixed_value"] = 999.0
            # 编辑器内不受影响
            out = ed.curves()
            assert out[0]["name"] == "加载"
            assert out[0]["points"][0]["fixed_value"] == 60.0
        finally:
            ed.deleteLater()

    def test_curves_returns_own_copy(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            r1 = ed.curves()
            r1[0]["name"] = "外部又改了"
            # 再取一次：应仍是原值
            r2 = ed.curves()
            assert r2[0]["name"] == "加载"
        finally:
            ed.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 增 / 复制 / 上下移
# ──────────────────────────────────────────────────────────────────
class TestListOps:
    def test_add_curve_appends(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._on_add_curve()
            assert len(ed.curves()) == 3
            assert ed._current_idx == 2
        finally:
            ed.deleteLater()

    def test_duplicate_curve(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_duplicate_curve()
            out = ed.curves()
            assert len(out) == 3
            # 副本插在源后，名带"(副本)"
            assert out[1]["name"] == "加载 (副本)"
            assert out[1]["points"] == out[0]["points"]
            assert ed._current_idx == 1
        finally:
            ed.deleteLater()

    def test_move_up_down(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 1
            ed._on_move_up()
            assert [c["name"] for c in ed.curves()] == ["卸载", "加载"]
            assert ed._current_idx == 0
            ed._on_move_down()
            assert [c["name"] for c in ed.curves()] == ["加载", "卸载"]
            assert ed._current_idx == 1
        finally:
            ed.deleteLater()

    def test_move_up_at_top_is_noop(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            names_before = [c["name"] for c in ed.curves()]
            ed._on_move_up()
            assert [c["name"] for c in ed.curves()] == names_before

        finally:
            ed.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 删除：MessageBox 二次确认
# ──────────────────────────────────────────────────────────────────
class TestDeleteWithConfirmation:
    def test_delete_proceeds_when_user_confirms(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from civ_core.ui.components import curves_editor as ce

        # 把 MessageBox.exec 改成"用户点了确认"
        monkeypatch.setattr(
            ce.MessageBox, "exec", lambda self: 1, raising=True
        )

        ed = ce.CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_delete_curve()
            out = ed.curves()
            assert len(out) == 1
            assert out[0]["name"] == "卸载"
        finally:
            ed.deleteLater()

    def test_delete_aborts_when_user_cancels(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from civ_core.ui.components import curves_editor as ce

        # 把 exec 改成"用户取消"
        monkeypatch.setattr(
            ce.MessageBox, "exec", lambda self: 0, raising=True
        )

        ed = ce.CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_delete_curve()
            assert len(ed.curves()) == 2  # 没删
        finally:
            ed.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 点序列：增、删、改
# ──────────────────────────────────────────────────────────────────
class TestPointsEditing:
    def test_add_point_appends(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_add_point()
            pts = ed.curves()[0]["points"]
            assert len(pts) == 3
            # 新点默认值
            assert pts[2]["fixed_axis"] == "y"
            assert pts[2]["fixed_value"] == 0.0
            assert pts[2]["var_column"] == ""
        finally:
            ed.deleteLater()

    def test_delete_point_removes_last_when_no_selection(
        self, qapp: QApplication
    ) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_delete_point()
            pts = ed.curves()[0]["points"]
            assert len(pts) == 1
            # 删了最后一行 → 留下第一行
            assert pts[0]["fixed_value"] == 60.0
        finally:
            ed.deleteLater()

    def test_point_value_change_writes_back(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            # 直接调内部 handler，模拟 cellWidget valueChanged
            ed._on_point_value_changed(0, 75.5)
            assert ed.curves()[0]["points"][0]["fixed_value"] == 75.5
        finally:
            ed.deleteLater()

    def test_point_axis_and_var_change(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            ed._on_point_axis_changed(1, "x")
            ed._on_point_var_changed(1, "120kN 位移")
            pt = ed.curves()[0]["points"][1]
            assert pt["fixed_axis"] == "x"
            assert pt["var_column"] == "120kN 位移"
        finally:
            ed.deleteLater()


# ──────────────────────────────────────────────────────────────────
# Excel 表头联动：LineEdit ⇄ ComboBox
# ──────────────────────────────────────────────────────────────────
class TestExcelHeadersBinding:
    def test_no_headers_uses_lineedit(self, qapp: QApplication) -> None:
        from civ_core.ui.components.curves_editor import (
            _POINT_COL_VAR,
            CurvesEditor,
        )

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            # 不挂载 headers
            cell = ed._points_table.cellWidget(0, _POINT_COL_VAR)
            assert isinstance(cell, QLineEdit)
        finally:
            ed.deleteLater()

    def test_with_headers_uses_combobox(self, qapp: QApplication) -> None:
        from qfluentwidgets import ComboBox as FluentComboBox

        from civ_core.ui.components.curves_editor import (
            _POINT_COL_VAR,
            CurvesEditor,
        )

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed.set_excel_headers(["编号", "60kN 位移", "90kN 位移", "120kN 位移"])
            cell = ed._points_table.cellWidget(0, _POINT_COL_VAR)
            # qfluentwidgets.ComboBox 不是 QComboBox 子类，这里用 fluent 那条
            assert isinstance(cell, FluentComboBox)
            # 当前值匹配上表头 → ComboBox 选中
            assert cell.currentText() == "60kN 位移"
        finally:
            ed.deleteLater()


# ──────────────────────────────────────────────────────────────────
# changed 信号：编辑时发，程序性刷新时不发
# ──────────────────────────────────────────────────────────────────
class TestChangedSignal:
    def test_set_curves_does_not_emit(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            with qtbot.assertNotEmitted(ed.changed, wait=200):
                ed.set_curves(_sample_curves())
        finally:
            ed.deleteLater()

    def test_add_point_emits(self, qapp: QApplication, qtbot: Any) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            with qtbot.waitSignal(ed.changed, timeout=500):
                ed._on_add_point()
        finally:
            ed.deleteLater()

    def test_point_value_change_emits(
        self, qapp: QApplication, qtbot: Any
    ) -> None:
        from civ_core.ui.components.curves_editor import CurvesEditor

        ed = CurvesEditor()
        try:
            ed.set_curves(_sample_curves())
            ed._current_idx = 0
            with qtbot.waitSignal(ed.changed, timeout=500):
                ed._on_point_value_changed(0, 100.0)
        finally:
            ed.deleteLater()
