"""P1.5-④ schema 扩展测试：CurveSeries.y_axis / y_err，PlotJob.y_axis2。

新字段语义：
  CurveSeries.y_axis: "primary"（默认，挂主 Y 轴）/ "secondary"（挂次 Y 轴）
  CurveSeries.y_err : None=无误差棒；非空时长度必须 == len(ys)，元素必须 >= 0
  PlotJob.y_axis2   : 次 Y 轴规格（AxisSpec | None）；None=不画双轴
"""

from __future__ import annotations

from pathlib import Path

import pytest

from civ_core.domain.schema import AxisSpec, CurveSeries, PlotJob


def _curve_factory(**override: object) -> CurveSeries:
    """造一条最小合法 CurveSeries，便于测试覆盖单一字段。"""
    kwargs: dict[str, object] = {
        "name": "s",
        "xs": [0.0, 1.0, 2.0],
        "ys": [0.0, 1.0, 2.0],
    }
    kwargs.update(override)
    return CurveSeries(**kwargs)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────
# CurveSeries.y_axis（双 Y 轴）
# ──────────────────────────────────────────────────────────────────
class TestYAxisField:
    def test_default_is_primary(self) -> None:
        s = _curve_factory()
        assert s.y_axis == "primary"

    def test_secondary_accepted(self) -> None:
        s = _curve_factory(y_axis="secondary")
        assert s.y_axis == "secondary"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="y_axis"):
            _curve_factory(y_axis="left")


# ──────────────────────────────────────────────────────────────────
# CurveSeries.y_err（误差棒）
# ──────────────────────────────────────────────────────────────────
class TestYErrField:
    def test_default_is_none(self) -> None:
        s = _curve_factory()
        assert s.y_err is None

    def test_same_length_accepted(self) -> None:
        s = _curve_factory(y_err=[0.1, 0.2, 0.3])
        assert s.y_err == [0.1, 0.2, 0.3]

    def test_length_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="y_err"):
            _curve_factory(y_err=[0.1, 0.2])  # ys 长度是 3

    def test_negative_value_rejected(self) -> None:
        """误差是离散量，必须非负。"""
        with pytest.raises(ValueError, match="y_err"):
            _curve_factory(y_err=[0.1, -0.05, 0.2])

    def test_zero_value_accepted(self) -> None:
        """允许 0（表示某点没有误差）。"""
        s = _curve_factory(y_err=[0.1, 0.0, 0.2])
        assert s.y_err is not None
        assert s.y_err[1] == 0.0


# ──────────────────────────────────────────────────────────────────
# PlotJob.y_axis2（双 Y 轴的次轴 spec）
# ──────────────────────────────────────────────────────────────────
class TestPlotJobYAxis2:
    def test_default_is_none(self) -> None:
        job = PlotJob(
            title="t",
            output_path=Path("a.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
        )
        assert job.y_axis2 is None

    def test_axis_spec_accepted(self) -> None:
        sec = AxisSpec(label="温度 (℃)", range=(0.0, 100.0, 20.0))
        job = PlotJob(
            title="t",
            output_path=Path("a.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
            y_axis2=sec,
        )
        assert job.y_axis2 is sec
