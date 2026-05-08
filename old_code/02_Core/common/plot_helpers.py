"""matplotlib 通用绘图工具。

只放纯函数：接收 PlotJob → 写出 PNG。
中文字体回退顺序：微软雅黑 / 黑体 / SimHei / Noto Sans CJK SC，最后兜底 sans-serif。
"""

import matplotlib

# 必须在 import pyplot 之前切到无 GUI 后端，避免 customtkinter 的 Tk 主循环冲突
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from common.types import PlotJob

# ============================================================
# 中文字体配置：matplotlib 默认 sans-serif 渲染中文会出方框，必须显式指定
# ============================================================
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
    """把可用的中文字体注入 matplotlib 的全局 rcParams。只配置一次。"""
    if getattr(_configure_chinese_font, "_done", False):
        return

    plt.rcParams["font.sans-serif"] = _CHINESE_FONT_CANDIDATES + ["sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False  # 负号能正确显示
    _configure_chinese_font._done = True


# ============================================================
# 绘图主函数
# ============================================================
def render_plot(
    job: PlotJob,
    figsize: tuple = (7, 4),
    dpi: int = 150,
    show_grid: bool = True,
    show_legend: bool = False,
    title_fontsize: int = 14,
    label_fontsize: int = 11,
) -> str:
    """把一个 PlotJob 渲染成 PNG，返回输出文件的绝对路径。

    figsize 单位英寸；dpi 越高越清晰。show_legend=False 因为参考样图里没有图例。
    """
    _configure_chinese_font()

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

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

    # 边框样式：四边都显示，细一点
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    fig.tight_layout()
    fig.savefig(job.output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return job.output_path


def _arange_inclusive(start: float, stop: float, step: float) -> list[float]:
    """像 numpy.arange 但包含 stop（避免浮点漂移）。"""
    out: list[float] = []
    n_steps = int(round((stop - start) / step))
    for i in range(n_steps + 1):
        out.append(start + i * step)
    return out
