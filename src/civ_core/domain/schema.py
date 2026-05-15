"""绘曲线图工具的核心业务数据契约。

为什么单独一份 domain/schema.py：
  • 旧 models/schema.py 把 7 个工具的契约堆在一起，PlotJob 只是其中一小段
  • 第 3 步只迁移绘曲线图相关的三个契约，与 v2.3 重构计划保持步幅
  • 校验全部放 __post_init__，禁止 pydantic（CLAUDE.md 总纲）

三个契约的关系：
  PlotJob (一张图)
    ├─ x_axis : AxisSpec
    ├─ y_axis : AxisSpec
    └─ series : list[CurveSeries]   每条曲线就是一组 (xs, ys) + 样式
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 接受 #RGB 与 #RRGGBB 两种十六进制颜色；matplotlib 还支持命名颜色，
# 但本工具的模板 JSON 里一直用 hex，统一限制反而更稳。
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


@dataclass(slots=True)
class AxisSpec:
    """坐标轴规格：标签 + 可选的固定范围 + 对数刻度开关。

    range=None 表示交给 matplotlib 自动选刻度。
    log=True 时启用 log10 刻度（与 range 同时启用须保证 min/max > 0）。
    """

    label: str
    range: tuple[float, float, float] | None = None
    log: bool = False

    def __post_init__(self) -> None:
        if self.range is None:
            return
        if len(self.range) != 3:
            raise ValueError(f"AxisSpec.range 必须是 (min, max, step) 三元组，得到 {self.range!r}")
        a_min, a_max, a_step = self.range
        if a_step <= 0:
            raise ValueError(f"AxisSpec.range 的 step 必须 > 0，得到 {a_step}")
        if a_min > a_max:
            raise ValueError(f"AxisSpec.range 必须 min <= max，得到 ({a_min}, {a_max})")


# 支持的图类型（土木场景覆盖）：
#   line    折线（默认）—— 经典荷载-位移 / 应力-应变曲线
#   scatter 散点 —— 试验数据分布 / 沉降观测点云
#   bar     柱状 —— 桩号-沉降 / 节点-承载力对比
#   step    阶梯 —— 位移-时间分级加载 / 阶梯荷载工况
_PLOT_TYPES = frozenset({"line", "scatter", "bar", "step"})

# P1.5-④ 双 Y 轴：CurveSeries 挂哪一个 Y 轴（默认主轴）
#   primary    —— 挂主 Y 轴（左边）；与单 Y 轴行为一致
#   secondary  —— 挂次 Y 轴（右边，twinx）；用于一图同时显示量纲不同的两组数据
#                 （如 荷载-位移 vs 时间-沉降；土壤围压 vs 应变）
_Y_AXES = frozenset({"primary", "secondary"})


@dataclass(slots=True)
class CurveSeries:
    """一条待绘制的曲线（已经把 Excel 一行展开成 (x, y) 序列）。

    样式字段对齐 matplotlib.lines.Line2D 的关键属性：
      color / marker / linewidth / markersize / plot_type

    P1.5-④ 新字段：
      y_axis : "primary" / "secondary" —— 挂主 / 次 Y 轴
      y_err  : 误差棒数据；None 表示无误差棒
    """

    name: str
    xs: list[float]
    ys: list[float]
    color: str = "#1F4FE0"
    marker: str = "s"
    linewidth: float = 2.0
    markersize: float = 7.0
    # 图类型：决定 chart_writer 走 ax.plot / scatter / bar / step
    plot_type: str = "line"
    # P1.5-④ 双 Y 轴：挂主 / 次 Y 轴
    y_axis: str = "primary"
    # P1.5-④ 误差棒：每点的 ±y 误差；None=不画误差棒
    # 非 None 时长度必须 == len(ys)；每个值 >= 0
    y_err: list[float] | None = None

    def __post_init__(self) -> None:
        if len(self.xs) != len(self.ys):
            raise ValueError(
                f"CurveSeries.xs / ys 长度必须相等，得到 xs={len(self.xs)} / ys={len(self.ys)}"
            )
        if self.linewidth <= 0:
            raise ValueError(f"CurveSeries.linewidth 必须 > 0，得到 {self.linewidth}")
        if self.markersize < 0:
            raise ValueError(f"CurveSeries.markersize 必须 >= 0，得到 {self.markersize}")
        if not _HEX_COLOR_RE.match(self.color):
            raise ValueError(f"CurveSeries.color 必须是 #RGB 或 #RRGGBB 形式，得到 {self.color!r}")
        if self.plot_type not in _PLOT_TYPES:
            raise ValueError(
                f"CurveSeries.plot_type 必须是 {sorted(_PLOT_TYPES)} 之一，得到 {self.plot_type!r}"
            )
        if self.y_axis not in _Y_AXES:
            raise ValueError(
                f"CurveSeries.y_axis 必须是 {sorted(_Y_AXES)} 之一，得到 {self.y_axis!r}"
            )
        if self.y_err is not None:
            if len(self.y_err) != len(self.ys):
                raise ValueError(
                    "CurveSeries.y_err 长度必须等于 ys，"
                    f"得到 y_err={len(self.y_err)} / ys={len(self.ys)}"
                )
            for i, e in enumerate(self.y_err):
                if e < 0:
                    raise ValueError(f"CurveSeries.y_err[{i}] 必须 >= 0，得到 {e}")


@dataclass(slots=True)
class PlotJob:
    """一张待输出图所需的全部信息（一行 Excel → 一张 PNG）。

    output_path：v2.3 总纲要求路径全部用 Path；__post_init__ 会把 str 自动包成 Path。
    grid / legend_loc：图级样式（来自 preset["style"]，与 AxisSpec.log 一道交给
    chart_writer 渲染时决定）；legend_loc=None 表示不显示图例。

    P1.5-④ y_axis2：次 Y 轴（双 Y 轴用，None=不画双轴）；
    匹配 series 里 y_axis="secondary" 的曲线挂到这一轴上。
    """

    title: str
    output_path: Path
    x_axis: AxisSpec
    y_axis: AxisSpec
    series: list[CurveSeries] = field(default_factory=list)
    grid: bool = True
    legend_loc: str | None = None
    # P1.5-④ 双 Y 轴的次 Y 轴规格；None 表示无（向后兼容）
    y_axis2: AxisSpec | None = None

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("PlotJob.title 不可为空")
        if not isinstance(self.output_path, Path):
            self.output_path = Path(self.output_path)
        if self.output_path.suffix == "":
            raise ValueError(
                f"PlotJob.output_path 必须带后缀（如 .png），得到 {self.output_path.name!r}"
            )


@dataclass
class PlotRunSettings:
    """绘曲线图的"运行级"配置：UI 设置面板 ↔ 本类 ↔ run_plot_curves 入参。

    与 PlotJob 的关系：
      PlotRunSettings = 用户在 UI 上选好的"准备跑批量的参数"
      PlotJob          = build_jobs 拿 PlotRunSettings + 预设 + 行数据后派生出的"一张图"
      所以 UI 双向绑的是这个 PlotRunSettings，不是 PlotJob 本身。

    所有字段允许为空：
      • 用户刚打开页面时啥都没选，不能让 dataclass 抛异常
      • 真正的"必填"校验放在点击"生成"按钮时（step 12 / 13），借 InfoBar 提示
    """

    input_path: Path | None = None
    sheet_name: str | None = None
    preset_name: str | None = None  # 由左栏 PresetListPane 推过来
    output_dir: Path | None = None
    header_row: int = 1

    def __post_init__(self) -> None:
        # 路径字段允许 str → Path 自动转，UI 取值方便
        if self.input_path is not None and not isinstance(self.input_path, Path):
            self.input_path = Path(self.input_path)
        if self.output_dir is not None and not isinstance(self.output_dir, Path):
            self.output_dir = Path(self.output_dir)
        if self.header_row < 1:
            raise ValueError(f"PlotRunSettings.header_row 必须 >= 1，得到 {self.header_row}")
