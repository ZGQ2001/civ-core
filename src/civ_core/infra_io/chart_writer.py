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
        for s in job.series:
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

        ax.set_title(job.title, fontsize=title_fontsize, fontweight="bold", pad=10)
        ax.set_xlabel(job.x_axis.label, fontsize=label_fontsize)
        ax.set_ylabel(job.y_axis.label, fontsize=label_fontsize)

        if job.x_axis.range is not None:
            x_min, x_max, x_step = job.x_axis.range
            ax.set_xlim(x_min, x_max)
            ax.set_xticks(_arange_inclusive(x_min, x_max, x_step))

        if job.y_axis.range is not None:
            y_min, y_max, y_step = job.y_axis.range
            ax.set_ylim(y_min, y_max)
            ax.set_yticks(_arange_inclusive(y_min, y_max, y_step))

        if show_grid:
            ax.grid(True, linestyle="-", linewidth=0.4, color="#CCCCCC", alpha=0.8)
            ax.set_axisbelow(True)
        if show_legend:
            ax.legend(loc="best", frameon=True)

        for spine in ax.spines.values():
            spine.set_linewidth(0.8)

        fig.tight_layout()

        # 走 atomic_writer：临时文件 → 原子替换。
        # 占用预检在 atomic_writer 入口完成；savefig 写到临时文件，最终 os.replace 到 job.output_path。
        # 临时文件后缀是 .tmp，matplotlib 无法从后缀推断格式，必须显式 format=
        fmt = job.output_path.suffix.lstrip(".").lower() or "png"
        with atomic_writer(job.output_path) as tmp:
            fig.savefig(str(tmp), dpi=dpi, bbox_inches="tight", format=fmt)

    log.debug("绘图完成: %s", job.output_path.name)
    return job.output_path
