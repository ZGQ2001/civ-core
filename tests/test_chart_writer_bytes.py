"""chart_writer.render_plot_to_bytes（L-2.2）单元测试。

只测"渲到 BytesIO"那一支：
  • 返回值是合法 PNG（magic bytes 校验）
  • job.output_path 没被读，因此可以传任意带后缀的占位路径
  • 共享 _configure_axes：与 render_plot_to_png 走同一份样式
"""

from __future__ import annotations

from pathlib import Path

from civ_core.domain.schema import AxisSpec, CurveSeries, PlotJob


def _make_job() -> PlotJob:
    return PlotJob(
        title="单元测试图",
        output_path=Path("dummy.png"),  # render_plot_to_bytes 不读这个字段
        x_axis=AxisSpec(label="位移", range=(0.0, 10.0, 2.0)),
        y_axis=AxisSpec(label="荷载", range=(0.0, 100.0, 20.0)),
        series=[
            CurveSeries(
                name="加载",
                xs=[0.0, 2.0, 4.0, 6.0],
                ys=[0.0, 20.0, 50.0, 80.0],
            )
        ],
    )


class TestRenderPlotToBytes:
    def test_returns_png_bytes(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        data = render_plot_to_bytes(_make_job())
        # PNG magic：\x89PNG\r\n\x1a\n
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        # 至少几百字节，太小说明 figure 没真画出来
        assert len(data) > 500

    def test_does_not_write_to_disk(self, tmp_path: Path) -> None:
        """output_path 字段被忽略，磁盘上不应出现文件。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        target = tmp_path / "shouldnt_exist.png"
        job = PlotJob(
            title="t",
            output_path=target,
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
            series=[CurveSeries(name="s", xs=[0.0], ys=[0.0])],
        )
        render_plot_to_bytes(job)
        assert not target.exists()

    def test_dpi_change_affects_output_size(self) -> None:
        """dpi=200 的输出比 dpi=50 大很多 —— 验证 dpi 参数生效。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        low = render_plot_to_bytes(_make_job(), dpi=50)
        high = render_plot_to_bytes(_make_job(), dpi=200)
        assert len(high) > len(low) * 1.5


# ──────────────────────────────────────────────────────────────────
# 多种 plot_type 都能渲染出 PNG
# ──────────────────────────────────────────────────────────────────
class TestPlotTypes:
    def test_each_plot_type_renders(self) -> None:
        """4 种 plot_type 都能产出合法 PNG。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        for plot_type in ("line", "scatter", "bar", "step"):
            job = PlotJob(
                title=f"plot_type={plot_type}",
                output_path=Path("dummy.png"),
                x_axis=AxisSpec(label="x"),
                y_axis=AxisSpec(label="y"),
                series=[
                    CurveSeries(
                        name="s",
                        xs=[1.0, 2.0, 3.0, 4.0],
                        ys=[1.0, 4.0, 2.0, 5.0],
                        plot_type=plot_type,
                    )
                ],
            )
            data = render_plot_to_bytes(job)
            assert data[:8] == b"\x89PNG\r\n\x1a\n", (
                f"plot_type={plot_type} 没产出合法 PNG"
            )

    def test_invalid_plot_type_rejected_at_schema(self) -> None:
        """CurveSeries 构造时即拦下非法 plot_type。"""
        import pytest

        with pytest.raises(ValueError, match="plot_type"):
            CurveSeries(
                name="x", xs=[0.0], ys=[0.0], plot_type="invalid_type"
            )


# ──────────────────────────────────────────────────────────────────
# AxisSpec.log / PlotJob.grid / PlotJob.legend_loc 透传到渲染
# ──────────────────────────────────────────────────────────────────
class TestAxisAndStyle:
    def test_log_scale_renders(self) -> None:
        """X/Y 同时启用对数刻度也能渲染出合法 PNG。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="log-log",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x", log=True),
            y_axis=AxisSpec(label="y", log=True),
            series=[
                CurveSeries(
                    name="s",
                    xs=[1.0, 10.0, 100.0],
                    ys=[1.0, 10.0, 100.0],
                )
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_legend_loc_renders(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="legend",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
            series=[CurveSeries(name="A", xs=[0.0, 1.0], ys=[0.0, 1.0])],
            legend_loc="upper left",
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
