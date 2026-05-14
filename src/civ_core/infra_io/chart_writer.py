"""绘曲线图的渲染落盘层（matplotlib + atomic_writer）。

为什么独立成模块（与 utils/plot_helpers.py 区别）：
  • core/ 层不允许直接 IO，fig.savefig 算写文件，所以必须放 infra_io/
  • Windows 下 PNG 经常被「照片」预览或杀毒进程独占，必须先经 file_manager 的占用预检，
    在写到一半时才报 PermissionError 已经太晚（目标会被截断成 0 字节）
  • matplotlib Figure 是有限资源，with-style 上下文确保异常路径上也 plt.close()

对外只暴露一个函数：
  render_plot_to_png(job, *, figsize, dpi, ...) -> Path
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

# 必须在 import pyplot 之前切到 Agg —— 没有 GUI 后端，避免与 PySide6 主循环抢消息队列
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from civ_core.domain.schema import AxisSpec, PlotJob
from civ_core.infra_io.file_manager import atomic_writer
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 中文字体候选：第一个能用的会被 matplotlib 选中
_CHINESE_FONT_CANDIDATES: list[str] = [
    "Microsoft YaHei",  # Windows 自带，覆盖最广
    "SimHei",  # Windows 黑体
    "DengXian",  # Windows 等线
    "FangSong",  # 仿宋
    "Noto Sans CJK SC",  # Linux
    "PingFang SC",  # macOS
    "Heiti SC",  # macOS 黑体
]


def _configure_chinese_font() -> None:
    """把中文字体注入 matplotlib 全局 rcParams（幂等，只配置一次）。

    放函数级 attribute 而不是模块级 flag，是为了让单元测试可以重置。
    """
    if getattr(_configure_chinese_font, "_done", False):
        return
    plt.rcParams["font.sans-serif"] = _CHINESE_FONT_CANDIDATES + ["sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    _configure_chinese_font._done = True  # type: ignore[attr-defined]
    log.debug("matplotlib 中文字体配置已注入")


@contextmanager
def _managed_figure(figsize: tuple[float, float], dpi: int) -> Iterator[tuple]:
    """plt.subplots 的 with-style 包装：异常路径也保证 plt.close(fig)。"""
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    try:
        yield fig, ax
    finally:
        plt.close(fig)


def _arange_inclusive(start: float, stop: float, step: float) -> list[float]:
    """像 numpy.arange 但包含 stop。

    用整数循环计数 + 乘法重构每个 tick，避免「累加 step」的浮点漂移
    （否则 0.0/0.1/0.2/...0.9 会变成 0.0/0.1/0.2/...0.8999999999999999）。
    """
    out: list[float] = []
    n_steps = int(round((stop - start) / step))
    for i in range(n_steps + 1):
        out.append(start + i * step)
    return out


def _draw_series(ax, s) -> None:
    """按 series.plot_type 调度到不同的 matplotlib 绘图方法。

    分支：
      line    ax.plot       折线 + marker（marker='' 时仅线）
      scatter ax.scatter    散点，无连线；markersize 用 s 参数（面积）
      bar     ax.bar        柱状；x 自动当柱中心，width 由 step 推测
      step    ax.step       阶梯线（where='post' 与土木分级加载工况一致）

    误差棒（P1.5-④）：series.y_err 非 None 时叠加 ax.errorbar 画黑色误差杠。
    step 类型不支持原生 errorbar，画了曲线后另起 errorbar(fmt='none')。
    """
    if s.plot_type == "scatter":
        # scatter 的 s 参数是点面积（按需放大约 markersize**2）
        ax.scatter(
            s.xs,
            s.ys,
            color=s.color,
            marker=s.marker,
            s=max(s.markersize, 1.0) ** 2,
            edgecolors=s.color,
            linewidths=1.0,
            label=s.name,
        )
    elif s.plot_type == "bar":
        # 柱宽估算：x 间距的 0.6 倍；x 单点时 fallback 1.0
        if len(s.xs) >= 2:
            spacing = min(abs(s.xs[i + 1] - s.xs[i]) for i in range(len(s.xs) - 1)) or 1.0
            width = spacing * 0.6
        else:
            width = 1.0
        ax.bar(
            s.xs,
            s.ys,
            color=s.color,
            width=width,
            edgecolor=s.color,
            linewidth=s.linewidth,
            label=s.name,
            yerr=s.y_err,  # None 时 matplotlib 自动忽略
            ecolor="#222222",
            capsize=3 if s.y_err else 0,
        )
    elif s.plot_type == "step":
        ax.step(
            s.xs,
            s.ys,
            where="post",
            color=s.color,
            linewidth=s.linewidth,
            marker=s.marker,
            markersize=s.markersize,
            markerfacecolor="white",
            markeredgecolor=s.color,
            markeredgewidth=1.5,
            label=s.name,
        )
    else:  # "line" 默认
        ax.plot(
            s.xs,
            s.ys,
            color=s.color,
            linewidth=s.linewidth,
            marker=s.marker,
            markersize=s.markersize,
            markerfacecolor="white",
            markeredgecolor=s.color,
            markeredgewidth=1.5,
            label=s.name,
        )

    # 误差棒（line / scatter / step 共用：单独叠 errorbar 画"杠"，不重画 marker）
    # bar 在 ax.bar(yerr=) 已经画过，跳过避免重复
    if s.y_err is not None and s.plot_type != "bar":
        ax.errorbar(
            s.xs,
            s.ys,
            yerr=s.y_err,
            fmt="none",
            ecolor="#222222",
            capsize=3,
            zorder=2,
        )


def _apply_axis_spec(ax, spec: AxisSpec, *, label_fontsize: int, axis: str) -> None:
    """把 AxisSpec 应用到给定 ax 的 X 或 Y 轴。

    axis: "x" / "y"（决定调 xlabel/xlim/xticks 还是 ylabel/ylim/yticks）
    抽取自原 _configure_axes，方便双 Y 轴复用（ax 主 / ax2 次共用同一套逻辑）。
    """
    if axis == "x":
        ax.set_xlabel(spec.label, fontsize=label_fontsize)
        if spec.log:
            ax.set_xscale("log")
        if spec.range is not None:
            a_min, a_max, a_step = spec.range
            ax.set_xlim(a_min, a_max)
            if not spec.log:
                ax.set_xticks(_arange_inclusive(a_min, a_max, a_step))
    else:  # "y"
        ax.set_ylabel(spec.label, fontsize=label_fontsize)
        if spec.log:
            ax.set_yscale("log")
        if spec.range is not None:
            a_min, a_max, a_step = spec.range
            ax.set_ylim(a_min, a_max)
            if not spec.log:
                ax.set_yticks(_arange_inclusive(a_min, a_max, a_step))


def _configure_axes(
    ax,
    job: PlotJob,
    *,
    show_grid: bool,
    show_legend: bool,
    title_fontsize: int,
    label_fontsize: int,
) -> None:
    """把 PlotJob 的样式 / 数据 / 轴配置应用到 Axes（落盘和 BytesIO 共用）。

    P1.5-④ 双 Y 轴：job.y_axis2 不为 None 时创建 ax2 = ax.twinx()，
    把 series 里 y_axis="secondary" 的曲线挂到 ax2。
    legend 合并：主轴 + 次轴 handles 拼接后只在主轴一次性 legend。
    """
    # 1) 准备双轴（如启用）
    ax2 = ax.twinx() if job.y_axis2 is not None else None
    # 双轴时 grid 默认只画主轴的，避免次轴 grid 叠加污染视觉
    # （ax.twinx() 默认隐藏次轴的 grid）

    # 2) 分发 series 到对应 axes
    for s in job.series:
        target = ax2 if (ax2 is not None and s.y_axis == "secondary") else ax
        _draw_series(target, s)

    # 3) 标题 + 主轴标签
    ax.set_title(job.title, fontsize=title_fontsize, fontweight="bold", pad=10)
    _apply_axis_spec(ax, job.x_axis, label_fontsize=label_fontsize, axis="x")
    _apply_axis_spec(ax, job.y_axis, label_fontsize=label_fontsize, axis="y")

    # 4) 次轴 spec（如启用）
    if ax2 is not None and job.y_axis2 is not None:
        _apply_axis_spec(ax2, job.y_axis2, label_fontsize=label_fontsize, axis="y")

    # 5) grid：只画主轴 grid（次轴 grid 与主轴叠加会显得乱）
    if job.grid if job.grid is not None else show_grid:
        ax.grid(True, linestyle="-", linewidth=0.4, color="#CCCCCC", alpha=0.8)
        ax.set_axisbelow(True)

    # 6) legend：双轴 → 合并 handles + labels；单轴沿用旧逻辑
    if ax2 is not None:
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        if h1 or h2:
            ax.legend(
                h1 + h2,
                l1 + l2,
                loc=job.legend_loc or ("best" if show_legend else "best"),
                frameon=True,
            )
    else:
        if job.legend_loc:
            ax.legend(loc=job.legend_loc, frameon=True)
        elif show_legend:
            ax.legend(loc="best", frameon=True)

    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    if ax2 is not None:
        for spine in ax2.spines.values():
            spine.set_linewidth(0.8)


def render_plot_to_png(
    job: PlotJob,
    *,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 150,
    show_grid: bool = True,
    show_legend: bool = False,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> Path:
    """把一个 PlotJob 渲染成 PNG 并原子写入 job.output_path。

    流程：
      1. configure 中文字体（幂等）
      2. 在受管 Figure 中画线 / 设标题 / 设轴
      3. 通过 atomic_writer 写入临时文件 → os.replace 到目标
         · 目标被占用：FileBusyError（带 hint）
         · 父目录不存在/不可写：FileWriteError

    返回值：写入成功的目标路径（与 job.output_path 一致）。
    """
    _configure_chinese_font()

    with _managed_figure(figsize, dpi) as (fig, ax):
        _configure_axes(
            ax,
            job,
            show_grid=show_grid,
            show_legend=show_legend,
            title_fontsize=title_fontsize,
            label_fontsize=label_fontsize,
        )
        fig.tight_layout()

        # 走 atomic_writer：临时文件 → 原子替换。
        # 占用预检在 atomic_writer 入口完成；savefig 写到临时文件，最终 os.replace 到 job.output_path。
        # 临时文件后缀是 .tmp，matplotlib 无法从后缀推断格式，必须显式 format=
        fmt = job.output_path.suffix.lstrip(".").lower() or "png"
        with atomic_writer(job.output_path) as tmp:
            fig.savefig(str(tmp), dpi=dpi, bbox_inches="tight", format=fmt)

    log.debug("绘图完成: %s", job.output_path.name)
    return job.output_path


# 叠加对比图色环（来自 matplotlib tab10，hex 化便于纯字符串处理）。
# 一根试件 = 一种颜色；超过 10 根循环复用（土木场景一次对比通常 < 20 根）。
_OVERLAY_PALETTE: list[str] = [
    "#1F77B4",
    "#FF7F0E",
    "#2CA02C",
    "#D62728",
    "#9467BD",
    "#8C564B",
    "#E377C2",
    "#7F7F7F",
    "#BCBD22",
    "#17BECF",
]


@dataclass(slots=True)
class SingleRowHitTestMeta:
    """单行预览图的 hit-testing 元数据（hover tooltip 用）。

    与叠加版 HitTestMeta 的差异：
      • 这里曲线区分用 series_name（"加载"/"卸载"），不区分 row idx
      • 多带 x_label / y_label，方便 UI 拼成 "位移=5.0 / 荷载=60.0" 的 tooltip
    """

    png_width: int
    png_height: int
    axes_bbox_px: tuple[float, float, float, float]
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    x_log: bool = False
    y_log: bool = False
    x_label: str = ""
    y_label: str = ""
    # 每条曲线：(series_name, xs, ys)
    curves: list[tuple[str, list[float], list[float]]] = field(default_factory=list)


@dataclass(slots=True)
class HitTestMeta:
    """叠加预览图的 hit-testing 元数据：让 UI 把 label 像素映射回 row_idx。

    所有像素坐标都基于 PNG 的左上原点（与 Qt QImage 一致）。

    字段：
      png_width / png_height : PNG 输出尺寸（像素）
      axes_bbox_px           : axes 在 PNG 中的矩形 (x0, y0, x1, y1)
      xlim / ylim            : data 坐标范围（线性轴用线性插值 / log 轴在 log10 域插值）
      x_log / y_log          : 对数轴标志
      points                 : [(row_idx, xs, ys), ...] 每根试件的全部 (x, y) 点
    """

    png_width: int
    png_height: int
    axes_bbox_px: tuple[float, float, float, float]
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    x_log: bool = False
    y_log: bool = False
    points: list[tuple[int, list[float], list[float]]] = field(default_factory=list)


def _draw_overlay_series(
    ax, s, *, color: str, alpha: float, zorder: int, lw_mul: float, label: str | None
) -> None:
    """叠加模式下绘一条 series：颜色 / 透明度 / 层级由调用方覆盖。

    与 _draw_series 的差异：
      • 强制覆盖 series.color —— 让同一根试件的所有曲线共用一种颜色
      • alpha / zorder / linewidth 倍率由调用方根据 highlight 状态决定
      • 一根试件只有第一条曲线带 label（避免 legend 重复"试件 A"三次）
    """
    if s.plot_type == "scatter":
        ax.scatter(
            s.xs,
            s.ys,
            color=color,
            marker=s.marker,
            s=max(s.markersize, 1.0) ** 2,
            edgecolors=color,
            linewidths=1.0,
            alpha=alpha,
            zorder=zorder,
            label=label,
        )
    elif s.plot_type == "bar":
        if len(s.xs) >= 2:
            spacing = min(abs(s.xs[i + 1] - s.xs[i]) for i in range(len(s.xs) - 1)) or 1.0
            width = spacing * 0.6
        else:
            width = 1.0
        ax.bar(
            s.xs,
            s.ys,
            color=color,
            width=width,
            edgecolor=color,
            linewidth=s.linewidth * lw_mul,
            alpha=alpha,
            zorder=zorder,
            label=label,
        )
    elif s.plot_type == "step":
        ax.step(
            s.xs,
            s.ys,
            where="post",
            color=color,
            linewidth=s.linewidth * lw_mul,
            marker=s.marker,
            markersize=s.markersize,
            markerfacecolor="white",
            markeredgecolor=color,
            markeredgewidth=1.5,
            alpha=alpha,
            zorder=zorder,
            label=label,
        )
    else:  # line
        ax.plot(
            s.xs,
            s.ys,
            color=color,
            linewidth=s.linewidth * lw_mul,
            marker=s.marker,
            markersize=s.markersize,
            markerfacecolor="white",
            markeredgecolor=color,
            markeredgewidth=1.5,
            alpha=alpha,
            zorder=zorder,
            label=label,
        )


def _render_overlay_core(
    jobs: list[PlotJob],
    *,
    highlight_row_idx: int,
    figsize: tuple[float, float],
    dpi: int,
    title: str | None,
    show_grid: bool,
    show_legend: bool,
    title_fontsize: int,
    label_fontsize: int,
    collect_hit_test: bool,
) -> tuple[bytes, HitTestMeta | None]:
    """叠加图共用核心：画图 + 输出 PNG +（可选）收集 hit-test 元数据。

    单独抽出是因为：
      • render_overlay_to_bytes 不要 meta（hover 关闭时不需要）
      • render_overlay_with_hittest 要 meta（hover 时把 label 像素映射回 row idx）
      • collect_hit_test=True 时，PNG 必须不裁剪（bbox_inches != 'tight'），
        否则 axes bbox 在 PNG 中的位置与 figure 像素不一致，反算会偏

    返回 (png_bytes, meta) —— collect_hit_test=False 时 meta=None。
    """
    if not jobs:
        raise ValueError("render_overlay: jobs 不可为空")

    _configure_chinese_font()

    base = jobs[0]
    final_title = title if title else f"叠加对比图（共 {len(jobs)} 根）"
    has_highlight = 0 <= highlight_row_idx < len(jobs)

    buf = io.BytesIO()
    meta: HitTestMeta | None = None

    with _managed_figure(figsize, dpi) as (fig, ax):
        for row_idx, job in enumerate(jobs):
            color = _OVERLAY_PALETTE[row_idx % len(_OVERLAY_PALETTE)]
            is_hl = has_highlight and row_idx == highlight_row_idx
            if is_hl:
                alpha, zorder, lw_mul = 1.0, 10, 1.8
            elif has_highlight:
                alpha, zorder, lw_mul = 0.4, 5, 1.0
            else:
                alpha, zorder, lw_mul = 0.85, 5, 1.0

            for s_idx, s in enumerate(job.series):
                label = job.title if s_idx == 0 else None
                _draw_overlay_series(
                    ax,
                    s,
                    color=color,
                    alpha=alpha,
                    zorder=zorder,
                    lw_mul=lw_mul,
                    label=label,
                )

        ax.set_title(final_title, fontsize=title_fontsize, fontweight="bold", pad=10)
        ax.set_xlabel(base.x_axis.label, fontsize=label_fontsize)
        ax.set_ylabel(base.y_axis.label, fontsize=label_fontsize)

        if base.x_axis.log:
            ax.set_xscale("log")
        if base.y_axis.log:
            ax.set_yscale("log")

        if base.x_axis.range is not None:
            x_min, x_max, x_step = base.x_axis.range
            ax.set_xlim(x_min, x_max)
            if not base.x_axis.log:
                ax.set_xticks(_arange_inclusive(x_min, x_max, x_step))

        if base.y_axis.range is not None:
            y_min, y_max, y_step = base.y_axis.range
            ax.set_ylim(y_min, y_max)
            if not base.y_axis.log:
                ax.set_yticks(_arange_inclusive(y_min, y_max, y_step))

        if base.grid if base.grid is not None else show_grid:
            ax.grid(True, linestyle="-", linewidth=0.4, color="#CCCCCC", alpha=0.8)
            ax.set_axisbelow(True)

        if base.legend_loc:
            ax.legend(loc=base.legend_loc, frameon=True, fontsize=9)
        elif show_legend:
            ax.legend(loc="best", frameon=True, fontsize=9)

        for spine in ax.spines.values():
            spine.set_linewidth(0.8)

        fig.tight_layout()

        if collect_hit_test:
            # 不能用 bbox_inches="tight"：那会裁掉留白，让 axes 在最终 PNG 中
            # 的像素位置脱离 fig.get_size_inches() × dpi 的天然对应。
            # 这里走"原汁原味"savefig，确保 axes_bbox_px 与 PNG 像素一致。
            fig.canvas.draw()  # 让 get_window_extent 拿到正确的 layout
            renderer = fig.canvas.get_renderer()
            ax_bbox = ax.get_window_extent(renderer=renderer)
            fig_w_px = int(round(fig.get_size_inches()[0] * fig.dpi))
            fig_h_px = int(round(fig.get_size_inches()[1] * fig.dpi))
            # matplotlib 坐标原点左下，PNG 原点左上 —— y 轴翻转
            x0_png = float(ax_bbox.x0)
            x1_png = float(ax_bbox.x1)
            y0_png = float(fig_h_px - ax_bbox.y1)
            y1_png = float(fig_h_px - ax_bbox.y0)

            xlim_t = ax.get_xlim()
            ylim_t = ax.get_ylim()
            points: list[tuple[int, list[float], list[float]]] = []
            for row_idx, job in enumerate(jobs):
                merged_xs: list[float] = []
                merged_ys: list[float] = []
                for s in job.series:
                    merged_xs.extend(s.xs)
                    merged_ys.extend(s.ys)
                points.append((row_idx, merged_xs, merged_ys))

            meta = HitTestMeta(
                png_width=fig_w_px,
                png_height=fig_h_px,
                axes_bbox_px=(x0_png, y0_png, x1_png, y1_png),
                xlim=(float(xlim_t[0]), float(xlim_t[1])),
                ylim=(float(ylim_t[0]), float(ylim_t[1])),
                x_log=base.x_axis.log,
                y_log=base.y_axis.log,
                points=points,
            )
            fig.savefig(buf, dpi=dpi, format="png")
        else:
            fig.savefig(buf, dpi=dpi, bbox_inches="tight", format="png")

    return buf.getvalue(), meta


def render_overlay_to_bytes(
    jobs: list[PlotJob],
    *,
    highlight_row_idx: int = -1,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 100,
    title: str | None = None,
    show_grid: bool = True,
    show_legend: bool = True,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> bytes:
    """渲染多根试件的叠加对比图为 PNG 字节流。

    语义：
      • 每个 PlotJob = 一根试件 = 叠加图上一种颜色（按 row idx 循环色环）
      • 同 job 的多条 series（如"加载/卸载"）共用颜色；只第一条带 legend label
      • highlight_row_idx 命中的 job：linewidth × 1.8、alpha=1.0、zorder=10
        其他 job：alpha=0.4（让高亮项视觉跳出）；未指定高亮（-1）时所有 0.85
      • axis label / range / log / grid / legend_loc 沿用 jobs[0]
      • title 可被 title 参数覆盖；为 None 时用 "叠加对比图（共 N 根）"

    本函数不收集 hit-test 元数据；要 hover 用 render_overlay_with_hittest。

    异常：jobs 为空 → ValueError（调用方应在投递 worker 前拦下）
    """
    png, _meta = _render_overlay_core(
        jobs,
        highlight_row_idx=highlight_row_idx,
        figsize=figsize,
        dpi=dpi,
        title=title,
        show_grid=show_grid,
        show_legend=show_legend,
        title_fontsize=title_fontsize,
        label_fontsize=label_fontsize,
        collect_hit_test=False,
    )
    return png


def render_overlay_with_hittest(
    jobs: list[PlotJob],
    *,
    highlight_row_idx: int = -1,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 100,
    title: str | None = None,
    show_grid: bool = True,
    show_legend: bool = True,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> tuple[bytes, HitTestMeta]:
    """同 render_overlay_to_bytes，但额外返回 HitTestMeta 用于鼠标 hover 反算。

    与无 meta 版的差异：
      • 输出 PNG 不裁剪（bbox_inches 不传 "tight"），让 axes 在 PNG 中的
        像素位置与 fig.dpi × figsize 严格对应；周围会有少量留白
      • 多算一次 fig.canvas.draw() + get_window_extent 拿 axes bbox

    返回 (png_bytes, hit_test_meta)。meta 字段见 HitTestMeta。
    """
    png, meta = _render_overlay_core(
        jobs,
        highlight_row_idx=highlight_row_idx,
        figsize=figsize,
        dpi=dpi,
        title=title,
        show_grid=show_grid,
        show_legend=show_legend,
        title_fontsize=title_fontsize,
        label_fontsize=label_fontsize,
        collect_hit_test=True,
    )
    assert meta is not None  # collect_hit_test=True 保证非空
    return png, meta


def render_plot_to_bytes(
    job: PlotJob,
    *,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 100,
    show_grid: bool = True,
    show_legend: bool = False,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> bytes:
    """渲染一个 PlotJob 为 PNG 字节流（不落盘），供 LivePreviewPane 实时预览。

    与 render_plot_to_png 的差异：
      • 不走 atomic_writer，savefig 直接写 BytesIO —— 实时预览高频触发，
        每次都落盘会把磁盘 IO 拉爆且产生大量孤儿文件
      • dpi 默认 100（落盘默认 150）—— 屏幕显示用，省 CPU 加速重绘
      • 仍复用 _configure_axes，保证预览和最终落盘的样式一致

    返回值：PNG 字节流（job.output_path 字段被忽略；本函数不读它）。
    """
    _configure_chinese_font()

    buf = io.BytesIO()
    with _managed_figure(figsize, dpi) as (fig, ax):
        _configure_axes(
            ax,
            job,
            show_grid=show_grid,
            show_legend=show_legend,
            title_fontsize=title_fontsize,
            label_fontsize=label_fontsize,
        )
        fig.tight_layout()
        # 直接渲到内存 buffer；不走 atomic_writer 也就不需要文件锁/原子替换
        fig.savefig(buf, dpi=dpi, bbox_inches="tight", format="png")

    return buf.getvalue()


def render_plot_with_hittest(
    job: PlotJob,
    *,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 100,
    show_grid: bool = True,
    show_legend: bool = False,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> tuple[bytes, SingleRowHitTestMeta]:
    """同 render_plot_to_bytes，但额外返回单行 hit-test meta（hover tooltip 用）。

    与 render_plot_to_bytes 的差异：
      • 不走 bbox_inches="tight"，让 PNG 留白固定 = figsize × dpi，
        axes 在 PNG 中的位置可精确反算
      • 多算一次 canvas.draw + get_window_extent 拿 axes 像素 bbox
    """
    _configure_chinese_font()

    buf = io.BytesIO()
    meta: SingleRowHitTestMeta
    with _managed_figure(figsize, dpi) as (fig, ax):
        _configure_axes(
            ax,
            job,
            show_grid=show_grid,
            show_legend=show_legend,
            title_fontsize=title_fontsize,
            label_fontsize=label_fontsize,
        )
        fig.tight_layout()

        # 拿 axes 像素 bbox（与叠加版同样的 y 翻转）
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        ax_bbox = ax.get_window_extent(renderer=renderer)
        fig_w_px = int(round(fig.get_size_inches()[0] * fig.dpi))
        fig_h_px = int(round(fig.get_size_inches()[1] * fig.dpi))
        x0_png = float(ax_bbox.x0)
        x1_png = float(ax_bbox.x1)
        y0_png = float(fig_h_px - ax_bbox.y1)
        y1_png = float(fig_h_px - ax_bbox.y0)

        xlim_t = ax.get_xlim()
        ylim_t = ax.get_ylim()
        curves: list[tuple[str, list[float], list[float]]] = []
        for s in job.series:
            curves.append((s.name, list(s.xs), list(s.ys)))

        meta = SingleRowHitTestMeta(
            png_width=fig_w_px,
            png_height=fig_h_px,
            axes_bbox_px=(x0_png, y0_png, x1_png, y1_png),
            xlim=(float(xlim_t[0]), float(xlim_t[1])),
            ylim=(float(ylim_t[0]), float(ylim_t[1])),
            x_log=job.x_axis.log,
            y_log=job.y_axis.log,
            x_label=job.x_axis.label,
            y_label=job.y_axis.label,
            curves=curves,
        )
        fig.savefig(buf, dpi=dpi, format="png")

    return buf.getvalue(), meta
