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
from pathlib import Path

import matplotlib

# 必须在 import pyplot 之前切到 Agg —— 没有 GUI 后端，避免与 PySide6 主循环抢消息队列
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from civ_core.domain.schema import PlotJob
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
            spacing = min(
                abs(s.xs[i + 1] - s.xs[i]) for i in range(len(s.xs) - 1)
            ) or 1.0
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

    show_grid / show_legend 是外部默认值；当 job.grid / job.legend_loc 显式
    指定时（来自 preset["style"]），优先用 job 的值。
    """
    for s in job.series:
        _draw_series(ax, s)

    ax.set_title(job.title, fontsize=title_fontsize, fontweight="bold", pad=10)
    ax.set_xlabel(job.x_axis.label, fontsize=label_fontsize)
    ax.set_ylabel(job.y_axis.label, fontsize=label_fontsize)

    # 对数刻度（如启用）—— 必须在 set_xticks 前调，否则刻度被 log 缩放搞乱
    if job.x_axis.log:
        ax.set_xscale("log")
    if job.y_axis.log:
        ax.set_yscale("log")

    if job.x_axis.range is not None:
        x_min, x_max, x_step = job.x_axis.range
        ax.set_xlim(x_min, x_max)
        # log 刻度下不手工 set_xticks（让 matplotlib 自适应 10/100/1000 等位置）
        if not job.x_axis.log:
            ax.set_xticks(_arange_inclusive(x_min, x_max, x_step))

    if job.y_axis.range is not None:
        y_min, y_max, y_step = job.y_axis.range
        ax.set_ylim(y_min, y_max)
        if not job.y_axis.log:
            ax.set_yticks(_arange_inclusive(y_min, y_max, y_step))

    # job.grid 优先于 show_grid 参数
    if job.grid if job.grid is not None else show_grid:
        ax.grid(True, linestyle="-", linewidth=0.4, color="#CCCCCC", alpha=0.8)
        ax.set_axisbelow(True)

    # legend：job.legend_loc 优先；为 None 但 show_legend=True 用 "best"
    if job.legend_loc:
        ax.legend(loc=job.legend_loc, frameon=True)
    elif show_legend:
        ax.legend(loc="best", frameon=True)

    for spine in ax.spines.values():
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
