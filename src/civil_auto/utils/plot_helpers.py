"""matplotlib 通用绘图工具（无 UI 依赖）。

工程规范落地：
  ✓ logger（不再 print）
  ✓ 全开类型注解
  ✓ figure 用 with-style 资源管理（plt.subplots 后 try/finally close）
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import matplotlib

# 必须在 import pyplot 之前切到无 GUI 后端，避免与 PySide6 主循环冲突
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from civil_auto.models.schema import PlotJob
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)

_CHINESE_FONT_CANDIDATES: list[str] = [
    "Microsoft YaHei",  # Windows 自带
    "SimHei",  # Windows 黑体
    "DengXian",  # Windows 等线
    "FangSong",  # 仿宋
    "Noto Sans CJK SC",  # Linux
    "PingFang SC",  # macOS
    "Heiti SC",  # macOS 黑体
]


def _configure_chinese_font() -> None:
    """把可用的中文字体注入 matplotlib 全局 rcParams（幂等，只配置一次）。"""
    if getattr(_configure_chinese_font, "_done", False):
        return
    plt.rcParams["font.sans-serif"] = _CHINESE_FONT_CANDIDATES + ["sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    _configure_chinese_font._done = True
    log.debug("matplotlib 中文字体配置已注入")


@contextmanager
def _managed_figure(figsize: tuple[float, float], dpi: int) -> Iterator[tuple]:
    """plt.subplots 的 with-style 包装：确保异常时也能 plt.close()。

    matplotlib 的 figure 是有限资源；忘记 close 会泄漏。
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    try:
        yield fig, ax
    finally:
        plt.close(fig)


def render_plot(
    job: PlotJob,
    figsize: tuple[float, float] = (7.0, 4.0),
    dpi: int = 150,
    show_grid: bool = True,
    show_legend: bool = False,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> Path:
    """把一个 PlotJob 渲染成 PNG，返回输出文件的绝对路径。"""
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

        out = Path(job.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=dpi, bbox_inches="tight")

    log.debug("绘图完成: %s", out.name)
    return out


def _arange_inclusive(start: float, stop: float, step: float) -> list[float]:
    """像 numpy.arange 但包含 stop（避免浮点漂移）。"""
    out: list[float] = []
    n_steps = int(round((stop - start) / step))
    for i in range(n_steps + 1):
        out.append(start + i * step)
    return out
