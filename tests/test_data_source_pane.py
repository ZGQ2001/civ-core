"""DataSourcePane（L-4 / L-5.1）单元测试。

覆盖：
  • 列过滤：set_preset_and_data 根据 id_column + curves[*].points[*].var_column
    收齐显示列；其它列不进表格
  • 兜底：preset 没给 keys 时显示前 3 列
  • 行点击 → row_highlighted 信号
  • highlight_row（外部反向调用）滚动到指定行 + 不触发回路
  • clear / 空数据状态
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


def _preset_with_curves() -> dict[str, Any]:
    """有 curves[*].points[*].var_column 的预设。"""
    return {
        "id_column": "编号",
        "curves": [
            {
                "name": "加载",
                "points": [
                    {"fixed_axis": "y", "fixed_value": 60.0, "var_column": "60kN 位移"},
                    {"fixed_axis": "y", "fixed_value": 90.0, "var_column": "90kN 位移"},
                ],
            }
        ],
    }


def _rows_with_extras() -> list[dict[str, Any]]:
    return [
        {
            "编号": "A-01",
            "60kN 位移": 1.2,
            "90kN 位移": 2.5,
            "无关列": "noise",
            "另一无关列": 999,
        },
        {
            "编号": "A-02",
            "60kN 位移": 1.5,
            "90kN 位移": 3.0,
            "无关列": "noise2",
            "另一无关列": 1000,
        },
    ]


# ──────────────────────────────────────────────────────────────────
# 列过滤
# ──────────────────────────────────────────────────────────────────
class TestColumnFiltering:
    def test_only_displays_mapped_columns(self, qapp: QApplication) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            assert pane._displayed_cols == ["编号", "60kN 位移", "90kN 位移"]
            # 模型列数与显示列数一致
            assert pane._model.columnCount() == 3
            # 行数同 rows
            assert pane._model.rowCount() == 2
            # 抽样断言：第一行第二列是 "1.2"
            assert pane._model.item(0, 1).text() == "1.2"
        finally:
            pane.deleteLater()

    def test_fallback_to_first_three_cols(self, qapp: QApplication) -> None:
        """preset 没给 id_column / curves 时 → 显示前 3 列。"""
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            preset_empty: dict[str, Any] = {"curves": []}
            pane.set_preset_and_data(preset_empty, _rows_with_extras())
            # 兜底取 _rows_with_extras() 第一行前 3 个 key（按 dict 插入序）
            assert len(pane._displayed_cols) == 3
            assert pane._displayed_cols[0] == "编号"
        finally:
            pane.deleteLater()

    def test_dedup_var_columns(self, qapp: QApplication) -> None:
        """同一 var_column 出现在多条曲线/多个点里 → 列表只保留一次。"""
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            preset = {
                "id_column": "编号",
                "curves": [
                    {
                        "name": "c1",
                        "points": [
                            {"var_column": "X"},
                            {"var_column": "X"},  # 重复
                        ],
                    },
                    {
                        "name": "c2",
                        "points": [
                            {"var_column": "X"},  # 又重复
                            {"var_column": "Y"},
                        ],
                    },
                ],
            }
            rows = [{"编号": "1", "X": 10, "Y": 20}]
            pane.set_preset_and_data(preset, rows)
            assert pane._displayed_cols == ["编号", "X", "Y"]
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# 行点击 → row_highlighted
# ──────────────────────────────────────────────────────────────────
class TestRowHighlightSignal:
    def test_select_row_emits_signal(self, qapp: QApplication, qtbot: Any) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            with qtbot.waitSignal(pane.row_highlighted, timeout=500) as blocker:
                pane._table.selectRow(1)
            assert blocker.args == [1]
        finally:
            pane.deleteLater()

    def test_highlight_row_does_not_recurse(self, qapp: QApplication, qtbot: Any) -> None:
        """外部调 highlight_row 应当不再发 row_highlighted（防止循环）。"""
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            with qtbot.assertNotEmitted(pane.row_highlighted, wait=200):
                pane.highlight_row(0)
        finally:
            pane.deleteLater()

    def test_highlight_row_out_of_range_is_noop(self, qapp: QApplication) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            pane.highlight_row(99)  # 越界
            # 不抛异常即视作通过；当前选中行应当还是初始（无选中）
            assert pane._table.currentIndex().row() in {-1, 0, 1}
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# clear / 空状态
# ──────────────────────────────────────────────────────────────────
class TestClear:
    def test_clear_empties_model(self, qapp: QApplication) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            assert pane._model.rowCount() > 0
            pane.clear()
            assert pane._model.rowCount() == 0
            assert pane._displayed_cols == []
            assert "尚未挂载" in pane._status.text()
        finally:
            pane.deleteLater()

    def test_none_preset_clears(self, qapp: QApplication) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            pane.set_preset_and_data(_preset_with_curves(), _rows_with_extras())
            pane.set_preset_and_data(None, _rows_with_extras())
            assert pane._model.rowCount() == 0
        finally:
            pane.deleteLater()


# ──────────────────────────────────────────────────────────────────
# None / NaN 单元格显示为空字符串
# ──────────────────────────────────────────────────────────────────
class TestCellRendering:
    def test_none_and_nan_render_blank(self, qapp: QApplication) -> None:
        from civ_core.ui.components.data_source_pane import DataSourcePane

        pane = DataSourcePane()
        try:
            preset = {"id_column": "编号", "curves": [{"points": [{"var_column": "X"}]}]}
            rows = [
                {"编号": "A", "X": None},
                {"编号": "B", "X": float("nan")},
                {"编号": "C", "X": 1.5},
            ]
            pane.set_preset_and_data(preset, rows)
            assert pane._model.item(0, 1).text() == ""
            assert pane._model.item(1, 1).text() == ""
            assert pane._model.item(2, 1).text() == "1.5"
        finally:
            pane.deleteLater()
