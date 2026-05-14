"""P1.5-④c core/plot_curves 解析新预设字段：y_axis2 / curve.y_axis / err_column。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from civ_core.core.plot_curves import (
    PlotCurvesError,
    _series_from_preset,
    build_jobs,
    resolve_columns,
)


def _preset_base() -> dict[str, Any]:
    """最小可工作预设，便于子测试 mutate。"""
    return {
        "id_column": "试件ID",
        "filename_function": "{id}.png",
        "filename_template": "{id}.png",
        "title_template": "{id}",
        "x_axis": {"label": "位移", "range": [0.0, 10.0, 2.0]},
        "y_axis": {"label": "荷载", "range": [0.0, 100.0, 20.0]},
        "curves": [
            {
                "name": "加载",
                "color": "#1F4FE0",
                "points": [
                    {"var_column": "X1", "fixed_axis": "y", "fixed_value": 0.0},
                    {"var_column": "X2", "fixed_axis": "y", "fixed_value": 50.0},
                    {"var_column": "X3", "fixed_axis": "y", "fixed_value": 100.0},
                ],
            },
        ],
    }


# ──────────────────────────────────────────────────────────────────
# y_axis2：预设可选；缺省 → None；存在 → AxisSpec
# ──────────────────────────────────────────────────────────────────
class TestYAxis2Parsing:
    def test_no_y_axis2_yields_none(self, tmp_path: Path) -> None:
        preset = _preset_base()
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        assert jobs[0].y_axis2 is None

    def test_y_axis2_parsed(self, tmp_path: Path) -> None:
        preset = _preset_base()
        preset["y_axis2"] = {
            "label": "温度 ℃",
            "range": [0.0, 500.0, 100.0],
            "log": False,
        }
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        assert jobs[0].y_axis2 is not None
        assert jobs[0].y_axis2.label == "温度 ℃"
        assert jobs[0].y_axis2.range == (0.0, 500.0, 100.0)


# ──────────────────────────────────────────────────────────────────
# curves[i].y_axis：默认 primary；可设 secondary
# ──────────────────────────────────────────────────────────────────
class TestCurveYAxisField:
    def test_default_primary(self, tmp_path: Path) -> None:
        preset = _preset_base()
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        assert jobs[0].series[0].y_axis == "primary"

    def test_secondary_propagated(self, tmp_path: Path) -> None:
        preset = _preset_base()
        preset["curves"][0]["y_axis"] = "secondary"
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        assert jobs[0].series[0].y_axis == "secondary"


# ──────────────────────────────────────────────────────────────────
# err_column：任一 point 有 → curve.y_err 非空
# ──────────────────────────────────────────────────────────────────
class TestErrorBarParsing:
    def test_no_err_column_yields_none(self, tmp_path: Path) -> None:
        preset = _preset_base()
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        assert jobs[0].series[0].y_err is None

    def test_err_column_collected(self, tmp_path: Path) -> None:
        preset = _preset_base()
        for i, pt in enumerate(preset["curves"][0]["points"]):
            pt["err_column"] = f"E{i + 1}"
        rows = [
            {
                "试件ID": "A",
                "X1": 0.0,
                "X2": 5.0,
                "X3": 10.0,
                "E1": 0.5,
                "E2": 1.0,
                "E3": 0.8,
            }
        ]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        s = jobs[0].series[0]
        assert s.y_err == [0.5, 1.0, 0.8]

    def test_partial_err_column(self, tmp_path: Path) -> None:
        """只配一个 point 的 err_column → 其他点填 0。"""
        preset = _preset_base()
        preset["curves"][0]["points"][1]["err_column"] = "E2"
        rows = [
            {
                "试件ID": "A",
                "X1": 0.0,
                "X2": 5.0,
                "X3": 10.0,
                "E2": 1.5,
            }
        ]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        s = jobs[0].series[0]
        assert s.y_err == [0.0, 1.5, 0.0]

    def test_err_column_missing_in_excel(self, tmp_path: Path) -> None:
        """err_column 在 Excel 中找不到（容差也未命中） → 该点填 0。
        注意：err_column 缺列会被 resolve_columns 列入 missing → build_jobs 抛
        PlotCurvesError；预期用 preflight_check 让用户先修。
        """
        preset = _preset_base()
        preset["curves"][0]["points"][0]["err_column"] = "NotExist"
        rows = [{"试件ID": "A", "X1": 0.0, "X2": 5.0, "X3": 10.0}]
        with pytest.raises(PlotCurvesError, match="找不到"):
            build_jobs(preset, rows, tmp_path)

    def test_err_column_non_numeric_falls_back_to_zero(self, tmp_path: Path) -> None:
        """err 列存在但值不是数字 → 该点误差填 0，其他点照常。"""
        preset = _preset_base()
        preset["curves"][0]["points"][1]["err_column"] = "E2"
        rows = [
            {
                "试件ID": "A",
                "X1": 0.0,
                "X2": 5.0,
                "X3": 10.0,
                "E2": "n/a",
            }
        ]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        s = jobs[0].series[0]
        # 没有任何 point 拿到合法 err → has_any_err 仍 False → y_err=None
        assert s.y_err is None

    def test_negative_err_clamped_to_zero(self, tmp_path: Path) -> None:
        preset = _preset_base()
        preset["curves"][0]["points"][0]["err_column"] = "E1"
        rows = [
            {
                "试件ID": "A",
                "X1": 0.0,
                "X2": 5.0,
                "X3": 10.0,
                "E1": -2.0,
            }
        ]
        jobs, _ = build_jobs(preset, rows, tmp_path)
        s = jobs[0].series[0]
        # -2 被 clamp 到 0；其他点本就 0；has_any_err 仍 True 因为列存在
        assert s.y_err == [0.0, 0.0, 0.0]


# ──────────────────────────────────────────────────────────────────
# resolve_columns 也参与 err_column
# ──────────────────────────────────────────────────────────────────
class TestResolveColumnsIncludesErr:
    def test_err_column_listed_in_needed(self) -> None:
        preset = _preset_base()
        preset["curves"][0]["points"][0]["err_column"] = "E1"
        cols = ["试件ID", "X1", "X2", "X3", "E1"]
        resolved, missing = resolve_columns(preset, cols)
        assert "E1" in resolved
        assert "E1" not in missing

    def test_err_column_missing_reported(self) -> None:
        preset = _preset_base()
        preset["curves"][0]["points"][0]["err_column"] = "Missing"
        cols = ["试件ID", "X1", "X2", "X3"]
        _resolved, missing = resolve_columns(preset, cols)
        assert "Missing" in missing


# ──────────────────────────────────────────────────────────────────
# _series_from_preset 直接调用
# ──────────────────────────────────────────────────────────────────
class TestSeriesFromPresetDirect:
    def test_basic_no_err_no_y_axis(self) -> None:
        curve = {
            "name": "c",
            "points": [
                {"var_column": "X", "fixed_axis": "y", "fixed_value": 0.0},
            ],
        }
        col_map = {"X": "X"}
        row = {"X": 1.5}
        s = _series_from_preset(curve, row, col_map)
        assert s is not None
        assert s.y_axis == "primary"
        assert s.y_err is None
