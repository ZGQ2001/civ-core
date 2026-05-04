"""跨模块流转的数据契约。

用 dataclass 取代裸 dict，IDE 能补全/跳转，字段改名一键全改。
"""

from dataclasses import dataclass, field


@dataclass
class PhotoPair:
    """已排序 Word 表格里一对"图 + 题注"在源表中的位置坐标（0-indexed）。

    img/txt 行列索引以 python-docx 的 row/cell 索引为准；
    传给 win32com 时要 +1（COM 是 1-indexed）。
    """

    num: int  # "图 N" 中的 N
    img_row_idx: int
    txt_row_idx: int
    img_col_idx: int
    txt_col_idx: int


@dataclass
class CurveSeries:
    """一条待绘制的曲线（已经把 Excel 数据展开成 (x, y) 序列）。"""

    name: str  # 图例名
    xs: list[float]
    ys: list[float]
    color: str = "#1F4FE0"
    marker: str = "s"
    linewidth: float = 2.0
    markersize: float = 7.0


@dataclass
class AxisSpec:
    """坐标轴：标签 + 可选的固定范围 (min, max, tick_step)。range=None 表示自动。"""

    label: str
    range: tuple[float, float, float] | None = None


@dataclass
class PlotJob:
    """一张待输出的图所需的全部信息。

    series 里通常 1~N 条曲线，画在同一坐标系里。
    """

    title: str
    output_path: str
    x_axis: AxisSpec
    y_axis: AxisSpec
    series: list[CurveSeries] = field(default_factory=list)
