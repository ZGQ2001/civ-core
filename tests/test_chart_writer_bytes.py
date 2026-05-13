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


# ──────────────────────────────────────────────────────────────────
# P1.5-Step2：render_overlay_to_bytes 多 jobs 叠加渲染
# ──────────────────────────────────────────────────────────────────
def _make_overlay_jobs(n: int) -> list[PlotJob]:
    """造 n 根试件的 jobs，title 区分 / xs.ys 略微偏移。"""
    jobs: list[PlotJob] = []
    for i in range(n):
        jobs.append(
            PlotJob(
                title=f"试件 {i + 1}",
                output_path=Path(f"j{i}.png"),
                x_axis=AxisSpec(label="位移", range=(0.0, 10.0, 2.0)),
                y_axis=AxisSpec(label="荷载", range=(0.0, 100.0, 20.0)),
                series=[
                    CurveSeries(
                        name="加载",
                        xs=[0.0, 2.0, 4.0, 6.0],
                        ys=[0.0 + i, 20.0 + i, 50.0 + i, 80.0 + i],
                    )
                ],
            )
        )
    return jobs


class TestRenderOverlayToBytes:
    def test_empty_jobs_raises(self) -> None:
        import pytest

        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        with pytest.raises(ValueError, match="jobs 不可为空"):
            render_overlay_to_bytes([])

    def test_single_job_renders(self) -> None:
        """单 job 也能用（虽然 view 此时会走单行模式，但 API 不限制）。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        data = render_overlay_to_bytes(_make_overlay_jobs(1))
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_multiple_jobs_renders(self) -> None:
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        data = render_overlay_to_bytes(_make_overlay_jobs(5))
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(data) > 500

    def test_highlight_in_range(self) -> None:
        """highlight_row_idx 命中应不崩，输出仍是 PNG。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        data = render_overlay_to_bytes(
            _make_overlay_jobs(4), highlight_row_idx=2
        )
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_highlight_out_of_range_does_not_crash(self) -> None:
        """越界 highlight_row_idx：视为"无高亮"，所有曲线正常透明度。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        # 大于 len(jobs) 与负数都允许（容错）
        for idx in (10, -1, 999):
            data = render_overlay_to_bytes(
                _make_overlay_jobs(3), highlight_row_idx=idx
            )
            assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_more_than_10_jobs_uses_palette_cycle(self) -> None:
        """颜色色环只有 10 色，>10 根试件应按 mod 循环不崩。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        data = render_overlay_to_bytes(_make_overlay_jobs(15))
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_log_axes_overlay(self) -> None:
        """叠加图也应支持对数轴（沿用 jobs[0] 的 axis）。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        jobs = []
        for i in range(3):
            jobs.append(
                PlotJob(
                    title=f"j{i}",
                    output_path=Path(f"j{i}.png"),
                    x_axis=AxisSpec(label="x", log=True),
                    y_axis=AxisSpec(label="y", log=True),
                    series=[CurveSeries(name="s", xs=[1.0, 10.0, 100.0], ys=[1.0, 10.0, 100.0])],
                )
            )
        data = render_overlay_to_bytes(jobs)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_custom_title_overrides_default(self) -> None:
        """显式传 title 应覆盖默认"叠加对比图（共 N 根）"。"""
        from civ_core.infra_io.chart_writer import render_overlay_to_bytes

        # 只能间接验证：自定义 title 时不崩 + 是 PNG
        # PNG 字节差异具体值不可移植断言
        data = render_overlay_to_bytes(
            _make_overlay_jobs(2), title="自定义对比图"
        )
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


# ──────────────────────────────────────────────────────────────────
# P1.5-Step3a：render_overlay_with_hittest 返回 PNG + 元数据
# ──────────────────────────────────────────────────────────────────
class TestRenderOverlayWithHittest:
    def test_returns_png_and_meta(self) -> None:
        from civ_core.infra_io.chart_writer import (
            HitTestMeta,
            render_overlay_with_hittest,
        )

        png, meta = render_overlay_with_hittest(_make_overlay_jobs(3))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert isinstance(meta, HitTestMeta)

    def test_meta_dimensions_match_figsize_dpi(self) -> None:
        """PNG 宽高 = figsize × dpi（不裁剪，留白保留）。"""
        from civ_core.infra_io.chart_writer import render_overlay_with_hittest

        png, meta = render_overlay_with_hittest(
            _make_overlay_jobs(2), figsize=(6.0, 4.0), dpi=100
        )
        assert meta.png_width == 600
        assert meta.png_height == 400

    def test_axes_bbox_inside_png(self) -> None:
        """axes bbox 在 PNG 范围内 + x0<x1, y0<y1。"""
        from civ_core.infra_io.chart_writer import render_overlay_with_hittest

        _png, meta = render_overlay_with_hittest(
            _make_overlay_jobs(2), figsize=(7.0, 4.0), dpi=100
        )
        x0, y0, x1, y1 = meta.axes_bbox_px
        assert 0 <= x0 < x1 <= meta.png_width
        assert 0 <= y0 < y1 <= meta.png_height
        # axes 通常占图面 50%~85%；用宽松界限：覆盖 30%+ 面积
        ax_area = (x1 - x0) * (y1 - y0)
        png_area = meta.png_width * meta.png_height
        assert ax_area / png_area > 0.3

    def test_meta_points_carry_all_rows(self) -> None:
        """meta.points 每根试件一项，row_idx 严格递增 + xs/ys 长度一致。"""
        from civ_core.infra_io.chart_writer import render_overlay_with_hittest

        jobs = _make_overlay_jobs(4)
        _png, meta = render_overlay_with_hittest(jobs)
        assert len(meta.points) == 4
        for i, (row_idx, xs, ys) in enumerate(meta.points):
            assert row_idx == i
            assert len(xs) == len(ys) == 4  # _make_overlay_jobs 每根 4 点

    def test_xlim_ylim_recorded(self) -> None:
        """显式 axis range 应反映到 meta.xlim/ylim。"""
        from civ_core.infra_io.chart_writer import render_overlay_with_hittest

        _png, meta = render_overlay_with_hittest(_make_overlay_jobs(2))
        # _make_overlay_jobs 用 (0, 10, 2) / (0, 100, 20)
        assert meta.xlim == (0.0, 10.0)
        assert meta.ylim == (0.0, 100.0)

    def test_empty_jobs_still_raises(self) -> None:
        import pytest

        from civ_core.infra_io.chart_writer import render_overlay_with_hittest

        with pytest.raises(ValueError, match="jobs 不可为空"):
            render_overlay_with_hittest([])


# ──────────────────────────────────────────────────────────────────
# P1.5-④ 单行 hover tooltip：render_plot_with_hittest + SingleRowHitTestMeta
# ──────────────────────────────────────────────────────────────────
class TestRenderPlotWithHittest:
    def test_returns_png_and_meta(self) -> None:
        from civ_core.infra_io.chart_writer import (
            SingleRowHitTestMeta,
            render_plot_with_hittest,
        )

        png, meta = render_plot_with_hittest(_make_job())
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert isinstance(meta, SingleRowHitTestMeta)

    def test_meta_dimensions_match_figsize_dpi(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        _png, meta = render_plot_with_hittest(
            _make_job(), figsize=(7.0, 4.0), dpi=100
        )
        assert meta.png_width == 700
        assert meta.png_height == 400

    def test_meta_carries_axis_labels(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        _png, meta = render_plot_with_hittest(_make_job())
        assert meta.x_label == "位移"
        assert meta.y_label == "荷载"

    def test_meta_carries_series(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        _png, meta = render_plot_with_hittest(_make_job())
        # _make_job 只有 1 条曲线"加载"，4 个点
        assert len(meta.curves) == 1
        name, xs, ys = meta.curves[0]
        assert name == "加载"
        assert len(xs) == len(ys) == 4

    def test_meta_axes_bbox_within_png(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        _png, meta = render_plot_with_hittest(_make_job())
        x0, y0, x1, y1 = meta.axes_bbox_px
        assert 0 <= x0 < x1 <= meta.png_width
        assert 0 <= y0 < y1 <= meta.png_height

    def test_meta_xlim_ylim_recorded(self) -> None:
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        _png, meta = render_plot_with_hittest(_make_job())
        # _make_job 用 (0, 10, 2) / (0, 100, 20)
        assert meta.xlim == (0.0, 10.0)
        assert meta.ylim == (0.0, 100.0)


# ──────────────────────────────────────────────────────────────────
# P1.5-④ 双 Y 轴 + 误差棒
# ──────────────────────────────────────────────────────────────────
class TestDualYAndErrorBar:
    def test_dual_y_renders(self) -> None:
        """job.y_axis2 不为 None → ax.twinx；y_axis='secondary' 的曲线挂次轴。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="dual y",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="时间", range=(0.0, 10.0, 2.0)),
            y_axis=AxisSpec(label="位移 (mm)", range=(0.0, 50.0, 10.0)),
            y_axis2=AxisSpec(label="温度 (℃)", range=(0.0, 100.0, 20.0)),
            series=[
                CurveSeries(
                    name="位移",
                    xs=[0.0, 2.0, 4.0, 6.0],
                    ys=[0.0, 10.0, 25.0, 40.0],
                    y_axis="primary",
                ),
                CurveSeries(
                    name="温度",
                    xs=[0.0, 2.0, 4.0, 6.0],
                    ys=[20.0, 35.0, 60.0, 80.0],
                    y_axis="secondary",
                ),
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_dual_y_log_scale_renders(self) -> None:
        """次轴对数也能渲染。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="dual y log",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y1"),
            y_axis2=AxisSpec(label="y2", log=True),
            series=[
                CurveSeries(name="a", xs=[1.0, 2.0], ys=[1.0, 2.0]),
                CurveSeries(name="b", xs=[1.0, 2.0], ys=[1.0, 100.0], y_axis="secondary"),
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_error_bar_line(self) -> None:
        """折线带误差棒。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="err line",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
            series=[
                CurveSeries(
                    name="带误差",
                    xs=[0.0, 1.0, 2.0, 3.0],
                    ys=[10.0, 20.0, 30.0, 40.0],
                    y_err=[1.0, 2.0, 1.5, 0.5],
                ),
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_error_bar_bar(self) -> None:
        """柱状图带误差棒。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="err bar",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y"),
            series=[
                CurveSeries(
                    name="柱+err",
                    xs=[1.0, 2.0, 3.0],
                    ys=[5.0, 7.0, 6.0],
                    y_err=[0.5, 0.4, 0.8],
                    plot_type="bar",
                ),
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_dual_y_with_error_bars(self) -> None:
        """双 Y + 主轴误差棒 + 次轴普通线，能渲。"""
        from civ_core.infra_io.chart_writer import render_plot_to_bytes

        job = PlotJob(
            title="combo",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x"),
            y_axis=AxisSpec(label="y1"),
            y_axis2=AxisSpec(label="y2"),
            series=[
                CurveSeries(
                    name="主",
                    xs=[0.0, 1.0, 2.0],
                    ys=[10.0, 20.0, 30.0],
                    y_err=[1.0, 2.0, 1.0],
                ),
                CurveSeries(
                    name="次",
                    xs=[0.0, 1.0, 2.0],
                    ys=[100.0, 80.0, 60.0],
                    y_axis="secondary",
                ),
            ],
        )
        data = render_plot_to_bytes(job)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_dual_y_with_hittest(self) -> None:
        """render_plot_with_hittest 也支持双 Y（meta.ylim 取主轴）。"""
        from civ_core.infra_io.chart_writer import render_plot_with_hittest

        job = PlotJob(
            title="t",
            output_path=Path("dummy.png"),
            x_axis=AxisSpec(label="x", range=(0.0, 10.0, 2.0)),
            y_axis=AxisSpec(label="y1", range=(0.0, 100.0, 20.0)),
            y_axis2=AxisSpec(label="y2", range=(0.0, 500.0, 100.0)),
            series=[
                CurveSeries(name="a", xs=[0.0, 5.0], ys=[10.0, 50.0]),
                CurveSeries(name="b", xs=[0.0, 5.0], ys=[100.0, 300.0], y_axis="secondary"),
            ],
        )
        png, meta = render_plot_with_hittest(job)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # meta.ylim 取主轴
        assert meta.ylim == (0.0, 100.0)
        # curves 仍是 2 条
        assert len(meta.curves) == 2
