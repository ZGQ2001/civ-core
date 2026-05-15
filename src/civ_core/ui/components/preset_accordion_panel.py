"""预设风琴参数面板（L-3b 实装 + UX 反馈重构）。

布局
====
六个自上而下的分组，全部装在 QScrollArea 内可滚动；末尾固定 stretch
保证全部折叠时分组紧贴顶部：
  1. 预设选择     —— 永远置顶；ComboBox + [+/复制/删除/保存]
  2. 数据源       —— Excel 路径 + sheet + 表头行号 + 输出目录
  3. 曲线定义     —— 装 L-3a 的 CurvesEditor
  4. 坐标轴       —— X/Y 轴标签 + range (min/max/step)
  5. 样式         —— 网格 + 图例位置
  6. 输出         —— 标识列 / 文件名 / 标题 / DPI

UX 取舍
=======
  • 长路径字段（Excel / 输出目录）使用"标签独占一行 + 控件+按钮另一行"，
    避免横向窗口宽度被占满后视觉割裂
  • 短字段（表头行号 / sheet）横向 2 列布局，节省高度
  • 分组 size policy 用 Maximum：折叠时只占标题高度，不强行撑层级
  • 整面板包 QScrollArea 防止内容溢出导致窗口锁定最小尺寸
  • 末尾 addStretch(1) 让分组靠顶（折叠所有分组时不会均分到中间）

接口
====
  • preset_changed         Signal(dict)                  预设字段全集改变
  • data_source_changed    Signal(object, object)        (Path | None, sheet | None)
  • request_redraw_signal  Signal()                      任意字段变化（防抖驱动 LivePreviewPane）
  • current_preset_data()  → dict                        当前预设字段（含 curves）
  • current_run_settings() → PlotRunSettings             当前运行时配置（含 sheet_name）
  • refresh()                                            重新加载预设列表

"最近使用预设"
==============
QSettings 键 `plot_curves/recent_presets` 存最近 5 个预设名（按时间倒序）。
ComboBox 把这些项加到列表最前并以「★」前缀标识。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    Slider,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
)

from civ_core.domain.schema import PlotRunSettings
from civ_core.infra_io.excel_reader import (
    ExcelReadError,
    get_column_headers,
    read_sheet_names,
)
from civ_core.infra_io.preset_manager import (
    PresetEntry,
    PresetError,
    PresetSource,
    copy_system_to_user,
    delete_user_preset,
    load_merged_presets,
    save_user_preset,
)
from civ_core.ui.components.curves_editor import CurvesEditor
from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 最近使用预设的容量：再多无意义（用户记不住第 6 条之外的）
_RECENT_PRESETS_MAX = 5
_SETTINGS_ORG = "ZGQ"
_SETTINGS_APP = "CivCore"
_SETTINGS_KEY_RECENT = "plot_curves/recent_presets"

# 图例位置候选（matplotlib 接受的字符串）
_LEGEND_LOC_CHOICES = (
    "best",
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "right",
    "center left",
    "center right",
    "lower center",
    "upper center",
    "center",
)

# 曲线级样式常量（迁自 curves_editor.py；统一在「样式/当前曲线」子段使用）
_QUICK_COLORS: tuple[str, ...] = (
    "#1F4FE0",  # 蓝
    "#E03A3A",  # 红
    "#1AAA55",  # 绿
    "#FFA500",  # 橙
    "#9C27B0",  # 紫
    "#000000",  # 黑
)
# matplotlib marker code → 人话显示
_MARKER_DISPLAY: tuple[tuple[str, str], ...] = (
    ("s", "■  方块"),
    ("o", "●  圆"),
    ("^", "▲  上三角"),
    ("v", "▼  下三角"),
    ("D", "◆  菱形"),
    ("x", "✕  叉"),
    ("*", "★  星"),
    ("+", "✚  加号"),
)
# 图类型 code → 人话显示
_PLOT_TYPE_DISPLAY: tuple[tuple[str, str], ...] = (
    ("line", "折线图（带数据点，标准曲线）"),
    ("scatter", "散点图（仅点，无连线）"),
    ("bar", "柱状图（桩号/节点对比）"),
    ("step", "阶梯图（分级加载工况）"),
)

# 新建预设的初始字段
_EMPTY_PRESET_DATA: dict[str, Any] = {
    "id_column": "编号",
    "filename_template": "{id}.png",
    "title_template": "{id}",
    "x_axis": {"label": "X", "range": None},
    "y_axis": {"label": "Y", "range": None},
    "curves": [],
}


def _compactify_widget(widget: QWidget, min_w: int) -> None:
    """让 widget 在 layout 中报告的 minimumSizeHint.width = min_w。

    问题背景：
      qfluentwidgets.ComboBox / qfluentwidgets.SpinBox 等控件默认 minimumSizeHint
      较大（ComboBox ≈ 212px、DoubleSpinBox（setRange=±1e9）≈ 324px），导致
      参数面板的 content widget 累加 minimumSize 远超 splitter 给的左栏宽度 →
      内部 widget 溢出 viewport → 按钮被截、字位移。

      单纯 widget.setMinimumWidth(min_w) 只设了"硬下限"属性，但 layout 在算
      minimumSize 时还是用 widget.minimumSizeHint()。所以同时需要覆盖
      minimumSizeHint 返回 (min_w, original_height) 才能真正让 layout 接受窄宽。

    用法：
      _compactify_widget(self._preset_combo, 100)  # 让 ComboBox 能压到 100px
      _compactify_widget(self._spin, 60)           # 让 SpinBox 能压到 60px

    实现是 monkey-patch 单个实例的 minimumSizeHint —— 不污染类，仅作用于该实例。
    """
    widget.setMinimumWidth(min_w)
    # 保留原方法获取自然高度；只压横向
    _orig = widget.minimumSizeHint

    def _capped() -> QSize:
        h = _orig().height()
        return QSize(min_w, h)

    widget.minimumSizeHint = _capped  # type: ignore[method-assign]


# ──────────────────────────────────────────────────────────────────
# 私有控件
# ──────────────────────────────────────────────────────────────────
class _SectionHeader(QWidget):
    """可折叠分组的标题栏 —— 固定宽度箭头 + 弹性标题文字。

    为什么不直接用 `ToolButton.setText(f"{arrow}  {title}")`：
      • `▾`(U+25BE) 和 `▸`(U+25B8) 是 small white/black 系列字符，**字面宽度
        和字形粗细都不同**。切换 expand 状态时整段文本（含 title）会左右
        晃动几像素，肉眼明显"跳"。这是用户报告的 bug。
      • 把箭头放进固定宽度的 QLabel（`setFixedWidth(14)`），title 在第二个
        QLabel 里 —— 不管箭头本身字形多大，title 起始位置不动。

    点击交互：mousePressEvent 转发 clicked 信号 + setCursor(PointingHand)。
    样式（左色条 / 卡片边框 / hover 背景）由 bootstrap._APP_QSS 的选择器
    `QWidget[objectName^="collapsibleSection_"] > QWidget#collapsibleHeader`
    统一接管，本类不写 inline QSS。
    """

    clicked = Signal()

    def __init__(
        self,
        title: str,
        *,
        collapsible: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleHeader")
        # WA_StyledBackground：让 QSS 的 background-color / hover 生效（默认
        # 纯 QWidget 不刷 styled background）
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._collapsible = collapsible
        self._expanded = True

        layout = QHBoxLayout(self)
        # padding 由 QSS 控制；本 layout 只留贴边
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 箭头标签：固定宽度 14px —— 切换字符不会撼动后续 title 的起点
        self._arrow_label = QLabel(self)
        self._arrow_label.setObjectName("collapsibleArrow")
        self._arrow_label.setFixedWidth(14)
        self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._arrow_label)

        # 标题标签
        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("collapsibleTitle")
        self._title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._title_label, 1)

        if collapsible:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_arrow()

    def set_expanded(self, expanded: bool) -> None:
        """状态切换：仅刷箭头字符，title 起点不动（这是本控件存在的意义）。"""
        self._expanded = expanded
        self._refresh_arrow()

    def _refresh_arrow(self) -> None:
        if not self._collapsible:
            self._arrow_label.setText("")  # 不可折叠分组：留空但仍占 14px 占位
            return
        # 同系列 BLACK TRIANGLE：U+25BC ▼ / U+25B6 ▶
        # 比 small 系列宽度差异小，且固定宽度容器二次兜底
        self._arrow_label.setText("▼" if self._expanded else "▶")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D401
        if self._collapsible and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _CollapsibleSection(QWidget):
    """可折叠分组：标题栏点击 → 展开/收起内容。

    Size policy 用 Maximum：折叠时只取标题高度，不被外层 layout 拉高。
    """

    def __init__(
        self,
        title: str,
        *,
        collapsible: bool = True,
        initially_expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(f"collapsibleSection_{title}")
        self._collapsible = collapsible
        self._expanded = initially_expanded
        # 关键：用 Maximum 让 widget 自己决定取最大高度（按内容），
        # 不被外层 QVBoxLayout 拉高；底部 addStretch(1) 吃掉剩余空间
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 标题栏：用 _SectionHeader（固定箭头 + 弹性标题），避免 ToolButton
        # 拼字符串时 ▾/▸ 字形宽度不同导致 title 起点抖动。
        self._header = _SectionHeader(title, collapsible=collapsible, parent=self)
        self._header.set_expanded(initially_expanded)
        if collapsible:
            self._header.clicked.connect(self._toggle)
        self._title = title
        outer.addWidget(self._header)

        # 内容容器
        self._body = QWidget(self)
        self._body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 6, 8, 8)
        self._body_layout.setSpacing(6)
        outer.addWidget(self._body)
        self._body.setVisible(initially_expanded)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._header.set_expanded(self._expanded)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def is_expanded(self) -> bool:
        return self._expanded


class _SliderInputRow(QWidget):
    """滑块 + DoubleSpinBox 双向联动控件。"""

    valueChanged = Signal(float)

    def __init__(
        self,
        *,
        minimum: float,
        maximum: float,
        step: float = 1.0,
        decimals: int = 1,
        initial: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scale = 10**decimals
        self._slider = Slider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(int(minimum * self._scale), int(maximum * self._scale))
        self._slider.setSingleStep(max(1, int(step * self._scale)))
        self._spin = DoubleSpinBox(self)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setDecimals(decimals)
        if initial is not None:
            self.setValue(initial)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, ival: int) -> None:
        v = ival / self._scale
        self._spin.blockSignals(True)
        try:
            self._spin.setValue(v)
        finally:
            self._spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_spin(self, v: float) -> None:
        self._slider.blockSignals(True)
        try:
            self._slider.setValue(int(v * self._scale))
        finally:
            self._slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self) -> float:
        return float(self._spin.value())

    def setValue(self, v: float) -> None:
        self._spin.blockSignals(True)
        self._slider.blockSignals(True)
        try:
            self._spin.setValue(v)
            self._slider.setValue(int(v * self._scale))
        finally:
            self._spin.blockSignals(False)
            self._slider.blockSignals(False)


class _RangeTrio(QWidget):
    """坐标轴范围三联控件：min / max / step + 启用开关。

    未启用 → 输出 None；启用 → 输出 [min, max, step]。
    """

    valueChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._enable = CheckBox("固定范围", self)
        self._min = DoubleSpinBox(self)
        self._min.setRange(-1e9, 1e9)
        self._min.setDecimals(3)
        self._max = DoubleSpinBox(self)
        self._max.setRange(-1e9, 1e9)
        self._max.setDecimals(3)
        self._step = DoubleSpinBox(self)
        self._step.setRange(0.001, 1e6)
        self._step.setDecimals(3)
        self._step.setValue(1.0)
        # 关键 bugfix：DoubleSpinBox 默认 sizeHint 按"能显示最长数字"算（≈ 324px
        # 当 range=(-1e9, 1e9)），3 个 spinbox + label 横排 minSize 累加 ≈ 1000px，
        # 远超 splitter 给的 280-300px → content widget 被撑大 → 「保存为我的预设」
        # 按钮被拉伸 / 字体位移。_compactify_widget 同时覆盖 minimumSizeHint 让
        # layout/splitter 看到 50px 的窄宽。
        for sb in (self._min, self._max, self._step):
            _compactify_widget(sb, 50)
        # 内部 widget 压缩后，_RangeTrio 整体 layout 算 minSize 仍偏大（spinbox 内部
        # spinner button + label + spacing 累加），需要再给整体设上限。180px 够装下
        # 3 个 50px spinbox + 3 个短 label + spacing
        # （在 outer = QVBoxLayout 之后调用，确保 layout 已 attach 才能算）

        # 两行布局：复选独占一行；min/max/step 一行（短字段并排）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(self._enable)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(BodyLabel("min", self))
        row.addWidget(self._min)
        row.addWidget(BodyLabel("max", self))
        row.addWidget(self._max)
        row.addWidget(BodyLabel("step", self))
        row.addWidget(self._step)
        outer.addLayout(row)

        self._enable.stateChanged.connect(self._on_enable_changed)
        for sb in (self._min, self._max, self._step):
            sb.valueChanged.connect(self._on_value_changed)
        self._set_enabled(False)

        # 给 _RangeTrio 整体也 compactify：内部 spinbox 压到 50 后，layout 算的
        # 整体 minSize 还有 spinner button + label 的累加（实测 310px）。直接
        # 覆盖本 widget 自身的 minimumSizeHint 让父 layout 看到 180px 的窄宽
        _compactify_widget(self, 180)

    def _set_enabled(self, on: bool) -> None:
        for sb in (self._min, self._max, self._step):
            sb.setEnabled(on)

    def _on_enable_changed(self, _state: int) -> None:
        self._set_enabled(self._enable.isChecked())
        self.valueChanged.emit()

    def _on_value_changed(self, _v: float) -> None:
        if self._enable.isChecked():
            self.valueChanged.emit()

    def get_range(self) -> list[float] | None:
        if not self._enable.isChecked():
            return None
        return [self._min.value(), self._max.value(), self._step.value()]

    def set_range(self, rng: list[float] | tuple[float, ...] | None) -> None:
        if rng is None:
            self._enable.setChecked(False)
            self._set_enabled(False)
            return
        self._enable.setChecked(True)
        self._set_enabled(True)
        if len(rng) >= 1:
            self._min.setValue(float(rng[0]))
        if len(rng) >= 2:
            self._max.setValue(float(rng[1]))
        if len(rng) >= 3:
            self._step.setValue(float(rng[2]))


def _vertical_field(label: str, *widgets: QWidget) -> QVBoxLayout:
    """长字段两行布局：上行标签，下行控件组。
    用于 Excel 路径 / 输出目录这种长字段，避免横向溢出。
    """
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(BodyLabel(label))
    if len(widgets) == 1:
        layout.addWidget(widgets[0])
    else:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for w in widgets:
            row.addWidget(w, 1 if isinstance(w, LineEdit) else 0)
        layout.addLayout(row)
    return layout


# ──────────────────────────────────────────────────────────────────
# 主组件：PresetAccordionPanel
# ──────────────────────────────────────────────────────────────────
class PresetAccordionPanel(QWidget):
    """六分组风琴式参数面板。"""

    # 当前预设字段全集（含 curves）变化时发出
    preset_changed = Signal(dict)
    # Excel 数据源 + sheet 变化时发出：(Path | None, str | None)
    data_source_changed = Signal(object, object)
    # 任何字段变化都发一次（view 用来防抖触发 LivePreviewPane.request_redraw）
    request_redraw_signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("presetAccordionPanel")
        # 整个面板可以被压缩；最小宽度限到一个合理值即可
        self.setMinimumWidth(280)

        # 内部状态
        self._entries: list[PresetEntry] = []
        self._suppress: bool = False
        self._current_preset_name: str | None = None

        # 运行时参数
        self._input_path: Path | None = None
        self._output_dir: Path | None = None
        self._sheet_name: str | None = None

        self._build_layout()
        self.refresh()

    # ── 顶层布局：QScrollArea 包内容容器 ─────────────────────────
    def _build_layout(self) -> None:
        # 外层：QScrollArea + 内容 widget
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        # widgetResizable 让内容横向自适应、竖向按内容高度滚
        self._scroll.setWidgetResizable(True)
        # 去掉边框噪音
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # 水平不滚（窗口窄时让内部 widget 自己收缩）
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 关键 bugfix：垂直滚动条强制 always-on。
        # 原因：默认 AsNeeded 在折叠/展开分组时滚动条会突然出现/消失，导致
        # viewport 宽度发生 ±N 像素跳变（N=滚动条宽度），所有内部 widget 跟着
        # 重排 —— 视觉表现就是用户报告的"展开列表时输入框宽度抖动、字位置变"。
        # 始终占位 + QSS 把滚动条做细，视觉影响远小于抖动。
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        outer.addWidget(self._scroll)

        # 内容容器
        content = QWidget()
        content.setObjectName("presetAccordionContent")
        self._scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        # 卡片化分组之间留 6px 呼吸空间 —— 配合 _APP_QSS 里的圆角白底卡片，
        # 制造"层叠卡片"的空间感，而不是粘成一坨方块
        layout.setSpacing(6)

        # 1. 预设选择（不可折叠）
        self._sec_preset = _CollapsibleSection("预设选择", collapsible=False, parent=content)
        self._build_preset_section(self._sec_preset.body_layout())
        layout.addWidget(self._sec_preset)

        # 2. 数据源
        self._sec_data = _CollapsibleSection("数据源", parent=content)
        self._build_data_section(self._sec_data.body_layout())
        layout.addWidget(self._sec_data)

        # 3. 曲线定义（默认收起，避免初次开屏被巨大编辑器占满）
        self._sec_curves = _CollapsibleSection("曲线定义", initially_expanded=False, parent=content)
        self._curves_editor = CurvesEditor(self)
        self._curves_editor.changed.connect(self._on_curves_changed)
        # 切曲线 / 增删 → 「样式 / 当前曲线」子段重载
        self._curves_editor.current_curve_changed.connect(self._on_current_curve_changed)
        self._sec_curves.body_layout().addWidget(self._curves_editor)
        layout.addWidget(self._sec_curves)

        # 4. 坐标轴
        self._sec_axis = _CollapsibleSection("坐标轴", initially_expanded=False, parent=content)
        self._build_axis_section(self._sec_axis.body_layout())
        layout.addWidget(self._sec_axis)

        # 5. 样式
        self._sec_style = _CollapsibleSection("样式", initially_expanded=False, parent=content)
        self._build_style_section(self._sec_style.body_layout())
        layout.addWidget(self._sec_style)

        # 6. 输出
        self._sec_out = _CollapsibleSection("输出", initially_expanded=False, parent=content)
        self._build_output_section(self._sec_out.body_layout())
        layout.addWidget(self._sec_out)

        # 末尾 stretch：分组全部折叠时把它们推到顶部，不会被外层均分
        layout.addStretch(1)

    # ── 1. 预设选择 ─────────────────────────────────────────────
    def _build_preset_section(self, layout: QVBoxLayout) -> None:
        self._preset_combo = ComboBox(self)
        # 关键 bugfix：qfluentwidgets.ComboBox 默认 minSizeHint ≈ 212px，
        # setMinimumWidth 单独无效（minSizeHint 仍按内部算）。用 _compactify
        # 同时覆盖 minimumSizeHint，让 splitter/layout 看到的 min 是 100
        _compactify_widget(self._preset_combo, 100)
        self._preset_combo.currentTextChanged.connect(self._on_preset_combo_changed)
        layout.addWidget(self._preset_combo)

        self._preset_status = BodyLabel("", self)
        self._preset_status.setStyleSheet("color: #888;")
        # 状态文本可能较长（如"来源：我的（保存后将存为「我的」预设）"），
        # 开启 wordWrap 让它换行 + 横向能压缩，避免撑大左栏
        self._preset_status.setWordWrap(True)
        _compactify_widget(self._preset_status, 0)
        layout.addWidget(self._preset_status)

        # 按钮分两行：第一行 新建/复制/删除；第二行 主操作保存
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._btn_new = PushButton("+新建", self)
        self._btn_new.clicked.connect(self._on_new_preset)
        btn_row.addWidget(self._btn_new)
        self._btn_copy = PushButton("复制", self)
        self._btn_copy.clicked.connect(self._on_copy_preset)
        btn_row.addWidget(self._btn_copy)
        self._btn_del = PushButton("删除", self)
        self._btn_del.clicked.connect(self._on_delete_preset)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._btn_save = PrimaryPushButton("保存为我的预设", self)
        self._btn_save.clicked.connect(self._on_save_preset)
        layout.addWidget(self._btn_save)

    # ── 2. 数据源 ────────────────────────────────────────────────
    def _build_data_section(self, layout: QVBoxLayout) -> None:
        # Excel 路径：标签独占一行 + LineEdit + 选择按钮
        self._input_path_edit = LineEdit(self)
        self._input_path_edit.setPlaceholderText("点击右侧按钮选择 Excel")
        self._input_path_edit.setReadOnly(True)
        btn_browse_in = PushButton("选择…", self)
        btn_browse_in.clicked.connect(self._on_pick_input_excel)
        layout.addLayout(_vertical_field("Excel 路径", self._input_path_edit, btn_browse_in))

        # Sheet + 表头行号：一行两个字段（栅格 2 列）
        short_grid = QGridLayout()
        short_grid.setContentsMargins(0, 0, 0, 0)
        short_grid.setHorizontalSpacing(8)
        short_grid.setVerticalSpacing(2)

        short_grid.addWidget(BodyLabel("Sheet", self), 0, 0)
        self._sheet_combo = ComboBox(self)
        self._sheet_combo.setPlaceholderText("先选 Excel")
        self._sheet_combo.setEnabled(False)
        # 同 preset_combo：compactify 让 minSizeHint = 80（layout/splitter 看到的）
        _compactify_widget(self._sheet_combo, 80)
        self._sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        short_grid.addWidget(self._sheet_combo, 1, 0)

        short_grid.addWidget(BodyLabel("表头行号", self), 0, 1)
        self._header_row_spin = SpinBox(self)
        self._header_row_spin.setRange(1, 50)
        self._header_row_spin.setValue(1)
        # SpinBox 默认 minSizeHint=142（按"50"显示宽算）；表头 1-50 范围 60px 够
        _compactify_widget(self._header_row_spin, 60)
        self._header_row_spin.valueChanged.connect(self._on_header_row_changed)
        short_grid.addWidget(self._header_row_spin, 1, 1)

        short_grid.setColumnStretch(0, 1)
        short_grid.setColumnStretch(1, 1)
        layout.addLayout(short_grid)

        # 输出目录：标签 + LineEdit + 选择按钮
        self._output_dir_edit = LineEdit(self)
        self._output_dir_edit.setPlaceholderText("批量出图的输出目录")
        self._output_dir_edit.setReadOnly(True)
        btn_browse_out = PushButton("选择…", self)
        btn_browse_out.clicked.connect(self._on_pick_output_dir)
        layout.addLayout(_vertical_field("输出目录", self._output_dir_edit, btn_browse_out))

    # ── 4. 坐标轴 ────────────────────────────────────────────────
    def _build_axis_section(self, layout: QVBoxLayout) -> None:
        # X / Y 各自一组：标签独占一行 + range 控件独占一行
        # （避免被横向挤到不可读）
        layout.addLayout(self._build_axis_block(axis="X"))
        layout.addLayout(self._build_axis_block(axis="Y"))
        # P1.5-④ 次 Y 轴（默认关；启用后双 Y 轴）
        layout.addLayout(self._build_y2_axis_block())

    def _build_axis_block(self, *, axis: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(BodyLabel(f"{axis} 轴标签", self))
        edit = LineEdit(self)
        edit.editingFinished.connect(self._on_axis_changed)
        col.addWidget(edit)

        rng = _RangeTrio(self)
        rng.valueChanged.connect(self._on_axis_changed)
        col.addWidget(rng)

        # 把控件挂回 self.* 让外部能读写
        if axis == "X":
            self._x_label_edit = edit
            self._x_range = rng
        else:
            self._y_label_edit = edit
            self._y_range = rng
        return col

    def _build_y2_axis_block(self) -> QVBoxLayout:
        """P1.5-④：次 Y 轴 block。启用 CheckBox 控制下面 label/range/log 字段可见。

        当未启用时 current_preset_data() 返回 y_axis2=None；
        启用时返回 {label, range, log} 字典（与 x_axis/y_axis 结构相同）。
        """
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        # CheckBox 文字尽量短：原"启用次 Y 轴（双 Y 轴对比）"按字宽算 minSize=253px，
        # 直接撑大左栏 → 按钮拉伸 + 字位移。缩短到"启用次 Y 轴"（≈ 120px），完整
        # 说明放 tooltip
        self._y2_enable_chk = CheckBox("启用次 Y 轴", self)
        self._y2_enable_chk.setToolTip("启用次 Y 轴：双 Y 轴对比图（左右两侧各一条数据轴）")
        self._y2_enable_chk.stateChanged.connect(self._on_y2_enable_changed)
        col.addWidget(self._y2_enable_chk)

        # 下面三块字段：用 QWidget 容器包起来，方便整体显隐
        self._y2_fields_widget = QWidget(self)
        y2_col = QVBoxLayout(self._y2_fields_widget)
        y2_col.setContentsMargins(0, 0, 0, 0)
        y2_col.setSpacing(2)

        y2_col.addWidget(BodyLabel("次 Y 轴标签", self))
        self._y2_label_edit = LineEdit(self._y2_fields_widget)
        self._y2_label_edit.editingFinished.connect(self._on_axis_changed)
        y2_col.addWidget(self._y2_label_edit)

        self._y2_range = _RangeTrio(self._y2_fields_widget)
        self._y2_range.valueChanged.connect(self._on_axis_changed)
        y2_col.addWidget(self._y2_range)

        self._y2_log_chk = CheckBox("次 Y 对数刻度", self._y2_fields_widget)
        self._y2_log_chk.stateChanged.connect(self._emit_preset_changed)
        y2_col.addWidget(self._y2_log_chk)

        col.addWidget(self._y2_fields_widget)
        # 启动时未启用 → 隐藏字段
        self._y2_fields_widget.setVisible(False)
        return col

    def _on_y2_enable_changed(self, _state: int) -> None:
        """次 Y 启用 / 关闭 → 显隐字段 + 触发预设变更（双 Y 图重渲染）。"""
        enabled = self._y2_enable_chk.isChecked()
        self._y2_fields_widget.setVisible(enabled)
        self._emit_preset_changed()

    # ── 5. 样式：两个子段（图级 + 当前曲线） ────────────────────
    def _build_style_section(self, layout: QVBoxLayout) -> None:
        # ── 子段 A：图级（对整张图生效） ──
        layout.addWidget(StrongBodyLabel("图级（整张图）", self))

        self._show_grid_chk = CheckBox("显示网格", self)
        self._show_grid_chk.setChecked(True)
        self._show_grid_chk.stateChanged.connect(self._emit_preset_changed)
        layout.addWidget(self._show_grid_chk)

        layout.addWidget(BodyLabel("图例位置", self))
        self._legend_combo = ComboBox(self)
        self._legend_combo.addItems(["关闭"] + list(_LEGEND_LOC_CHOICES))
        self._legend_combo.setCurrentText("关闭")
        self._legend_combo.currentTextChanged.connect(self._emit_preset_changed)
        layout.addWidget(self._legend_combo)

        # 对数刻度：土木场景常见（应力-应变对数曲线、振动衰减等）
        layout.addWidget(BodyLabel("坐标刻度", self))
        log_row = QHBoxLayout()
        log_row.setContentsMargins(0, 0, 0, 0)
        log_row.setSpacing(12)
        self._x_log_chk = CheckBox("X 对数", self)
        self._x_log_chk.setToolTip("X 轴用 log10 刻度（如频率、应变率）")
        self._x_log_chk.stateChanged.connect(self._emit_preset_changed)
        log_row.addWidget(self._x_log_chk)
        self._y_log_chk = CheckBox("Y 对数", self)
        self._y_log_chk.setToolTip("Y 轴用 log10 刻度（如振幅衰减、应力）")
        self._y_log_chk.stateChanged.connect(self._emit_preset_changed)
        log_row.addWidget(self._y_log_chk)
        log_row.addStretch(1)
        layout.addLayout(log_row)

        # ── 子段 B：当前曲线（跟随曲线定义里选中的曲线变） ──
        # 切曲线时 CurvesEditor.current_curve_changed → _on_current_curve_changed
        # 在这里刷新；本子段所有字段的修改会回写到 CurvesEditor.curves[idx]
        layout.addWidget(BodyLabel("", self))  # 间距
        layout.addWidget(StrongBodyLabel("当前曲线（仅作用于选中曲线）", self))

        self._curve_style_hint = BodyLabel("（请先在「曲线定义」分组选一条）", self)
        self._curve_style_hint.setStyleSheet("color: #888;")
        layout.addWidget(self._curve_style_hint)

        # 整个"当前曲线"区放到一个 widget 里，便于 setEnabled 整体禁用
        self._curve_style_box = QWidget(self)
        cs_layout = QVBoxLayout(self._curve_style_box)
        cs_layout.setContentsMargins(0, 0, 0, 0)
        cs_layout.setSpacing(4)
        layout.addWidget(self._curve_style_box)

        # 图类型
        cs_layout.addWidget(BodyLabel("图类型", self))
        self._curve_plot_type_combo = ComboBox(self)
        for code, display in _PLOT_TYPE_DISPLAY:
            self._curve_plot_type_combo.addItem(display, userData=code)
        self._curve_plot_type_combo.setToolTip(
            "折线：标准曲线（荷载-位移、应力-应变）\n"
            "散点：试验数据分布 / 沉降观测点云\n"
            "柱状：桩号-沉降 / 节点-承载力对比\n"
            "阶梯：分级加载工况（位移-时间）"
        )
        self._curve_plot_type_combo.currentIndexChanged.connect(
            lambda _i: self._on_curve_style_field_changed(
                "plot_type", self._curve_plot_type_combo.currentData() or "line"
            )
        )
        cs_layout.addWidget(self._curve_plot_type_combo)

        # 颜色（6 个快选 + 更多...）
        cs_layout.addWidget(BodyLabel("颜色", self))
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(4)
        self._curve_color_swatches: list[QPushButton] = []
        for hex_color in _QUICK_COLORS:
            btn = QPushButton(self)
            btn.setFixedSize(24, 24)
            btn.setProperty("colorHex", hex_color)
            btn.setToolTip(hex_color)
            btn.clicked.connect(
                lambda _=False, c=hex_color: self._on_curve_style_field_changed("color", c)
            )
            color_row.addWidget(btn)
            self._curve_color_swatches.append(btn)
        self._btn_curve_color_more = PushButton("更多…", self)
        self._btn_curve_color_more.clicked.connect(self._on_curve_color_dialog)
        color_row.addWidget(self._btn_curve_color_more)
        color_row.addStretch(1)
        cs_layout.addLayout(color_row)

        # 点形状
        cs_layout.addWidget(BodyLabel("点形状", self))
        self._curve_marker_combo = ComboBox(self)
        for code, display in _MARKER_DISPLAY:
            self._curve_marker_combo.addItem(display, userData=code)
        self._curve_marker_combo.setToolTip(
            "图形 = 视觉示意；存盘是 matplotlib marker code (s/o/^/v 等)"
        )
        self._curve_marker_combo.currentIndexChanged.connect(
            lambda _i: self._on_curve_style_field_changed(
                "marker", self._curve_marker_combo.currentData() or "s"
            )
        )
        cs_layout.addWidget(self._curve_marker_combo)

        # 线宽 + 点大小（一行两个）
        cs_layout.addWidget(BodyLabel("线宽  /  点大小", self))
        sizes_row = QHBoxLayout()
        sizes_row.setContentsMargins(0, 0, 0, 0)
        sizes_row.setSpacing(8)
        self._curve_linewidth_spin = DoubleSpinBox(self)
        self._curve_linewidth_spin.setRange(0.1, 10.0)
        self._curve_linewidth_spin.setSingleStep(0.5)
        self._curve_linewidth_spin.setDecimals(1)
        self._curve_linewidth_spin.valueChanged.connect(
            lambda v: self._on_curve_style_field_changed("linewidth", float(v))
        )
        sizes_row.addWidget(self._curve_linewidth_spin)
        self._curve_markersize_spin = DoubleSpinBox(self)
        self._curve_markersize_spin.setRange(0.0, 20.0)
        self._curve_markersize_spin.setSingleStep(0.5)
        self._curve_markersize_spin.setDecimals(1)
        self._curve_markersize_spin.valueChanged.connect(
            lambda v: self._on_curve_style_field_changed("markersize", float(v))
        )
        sizes_row.addWidget(self._curve_markersize_spin)
        cs_layout.addLayout(sizes_row)

        # 初始状态：无选中曲线 → 整体 disabled
        self._curve_style_box.setEnabled(False)

    # ── 6. 输出 ──────────────────────────────────────────────────
    def _build_output_section(self, layout: QVBoxLayout) -> None:
        # 标识列
        layout.addWidget(BodyLabel("标识列名（Excel 中作为「id」的列）", self))
        self._id_column_edit = LineEdit(self)
        self._id_column_edit.editingFinished.connect(self._emit_preset_changed)
        layout.addWidget(self._id_column_edit)

        # 文件名模板
        layout.addWidget(BodyLabel("文件名模板（含 {id} 占位）", self))
        self._fname_edit = LineEdit(self)
        self._fname_edit.setPlaceholderText("如  锚杆{id}_曲线.png")
        self._fname_edit.editingFinished.connect(self._emit_preset_changed)
        layout.addWidget(self._fname_edit)

        # 标题模板
        layout.addWidget(BodyLabel("图标题模板", self))
        self._title_edit = LineEdit(self)
        self._title_edit.setPlaceholderText("如  锚杆{id}：曲线")
        self._title_edit.editingFinished.connect(self._emit_preset_changed)
        layout.addWidget(self._title_edit)

        # DPI 滑块
        layout.addWidget(BodyLabel("PNG 输出 DPI", self))
        self._dpi_row = _SliderInputRow(
            minimum=50.0,
            maximum=400.0,
            step=10.0,
            decimals=0,
            initial=150.0,
            parent=self,
        )
        self._dpi_row.valueChanged.connect(self._emit_request_redraw)
        layout.addWidget(self._dpi_row)

    # ── 信号转发 ─────────────────────────────────────────────────
    def _emit_preset_changed(self) -> None:
        if self._suppress:
            return
        self.preset_changed.emit(self.current_preset_data())
        self.request_redraw_signal.emit()

    def _emit_request_redraw(self) -> None:
        if self._suppress:
            return
        self.request_redraw_signal.emit()

    def _emit_data_source_changed(self) -> None:
        if self._suppress:
            return
        self.data_source_changed.emit(self._input_path, self._sheet_name)
        self.request_redraw_signal.emit()

    def _on_axis_changed(self) -> None:
        self._emit_preset_changed()

    def _on_curves_changed(self) -> None:
        self._emit_preset_changed()

    # ── 「样式 / 当前曲线」子段：与 CurvesEditor 双向同步 ────────
    def _on_current_curve_changed(self, idx: int) -> None:
        """CurvesEditor 切曲线 / 增删 / 上下移时调用。

        从当前选中曲线读字段刷到样式区控件；无选中曲线时整段 disabled。
        """
        curve = self._curves_editor.current_curve_data()
        if curve is None:
            self._curve_style_hint.setText("（请先在「曲线定义」分组选一条）")
            self._curve_style_box.setEnabled(False)
            return
        name = str(curve.get("name", f"#{idx + 1}"))
        self._curve_style_hint.setText(f"当前：#{idx + 1}  {name}（修改下方字段实时反映到该曲线）")
        self._curve_style_box.setEnabled(True)
        self._load_curve_style(curve)

    def _load_curve_style(self, curve: dict[str, Any]) -> None:
        """把曲线字段铺到样式区控件。suppress 期间不触发回写。"""
        self._suppress = True
        try:
            # plot_type
            plot_type = str(curve.get("plot_type", "line"))
            for i in range(self._curve_plot_type_combo.count()):
                if self._curve_plot_type_combo.itemData(i) == plot_type:
                    self._curve_plot_type_combo.setCurrentIndex(i)
                    break
            # marker
            marker = str(curve.get("marker", "s"))
            for i in range(self._curve_marker_combo.count()):
                if self._curve_marker_combo.itemData(i) == marker:
                    self._curve_marker_combo.setCurrentIndex(i)
                    break
            # 线宽 / 点大小
            try:
                self._curve_linewidth_spin.setValue(float(curve.get("linewidth", 2.0)))
            except (TypeError, ValueError):
                self._curve_linewidth_spin.setValue(2.0)
            try:
                self._curve_markersize_spin.setValue(float(curve.get("markersize", 7.0)))
            except (TypeError, ValueError):
                self._curve_markersize_spin.setValue(7.0)
            # 颜色快选高亮
            self._update_curve_swatches(str(curve.get("color", "#1F4FE0")))
        finally:
            self._suppress = False

    def _update_curve_swatches(self, current_hex: str) -> None:
        """6 个色块按钮：当前色匹配的加 3px 黑边高亮。"""
        cur = current_hex.upper()
        for btn in self._curve_color_swatches:
            hex_color = str(btn.property("colorHex") or "").upper()
            is_current = hex_color == cur
            btn.setStyleSheet(
                f"QPushButton {{ background: {hex_color}; "
                f"  border: {'3px solid #000' if is_current else '1px solid #888'}; "
                f"  border-radius: 3px; }}"
                f"QPushButton:hover {{ border: 2px solid #333; }}"
            )

    def _on_curve_style_field_changed(self, key: str, value: Any) -> None:
        """样式区任意字段变化 → 回写当前曲线 + 触发预览重绘。"""
        if self._suppress:
            return
        self._curves_editor.update_current_curve_field(key, value)
        # 颜色变化时刷新色块高亮
        if key == "color":
            self._update_curve_swatches(str(value))
        self._emit_preset_changed()

    def _on_curve_color_dialog(self) -> None:
        """点击"更多…" → QColorDialog 选自定义色 → 写回。"""
        curve = self._curves_editor.current_curve_data()
        if curve is None:
            return
        cur = QColor(str(curve.get("color", "#1F4FE0")))
        chosen = QColorDialog.getColor(cur, self, "选择曲线颜色")
        if chosen.isValid():
            self._on_curve_style_field_changed("color", chosen.name())

    def _on_sheet_changed(self, sheet: str) -> None:
        if self._suppress:
            return
        self._sheet_name = sheet or None
        # 切 sheet 后表头可能完全不一样 → 重读
        self._refresh_excel_headers()
        self._emit_data_source_changed()

    def _on_header_row_changed(self, _v: int) -> None:
        """表头行号变化 → 重读 Excel 表头喂 CurvesEditor + 触发重绘。"""
        if self._suppress:
            return
        self._refresh_excel_headers()
        self._emit_request_redraw()

    # ── 预设 ComboBox 交互 ───────────────────────────────────────
    def refresh(self, select_name: str | None = None) -> None:
        try:
            self._entries = load_merged_presets("plot_curves")
        except PresetError as e:
            log.error("加载预设失败：%s", e)
            self._entries = []

        recent = self._load_recent_names()
        recent_set = set(recent)
        recent_in_list = [e for n in recent for e in self._entries if e.name == n]
        rest = [e for e in self._entries if e.name not in recent_set]
        ordered = recent_in_list + rest

        self._suppress = True
        try:
            self._preset_combo.clear()
            for e in ordered:
                mark = "★ " if e.name in recent_set else ""
                self._preset_combo.addItem(f"{mark}{e.name}", userData=e.name)

            target = select_name or self._current_preset_name
            if target and any(e.name == target for e in ordered):
                for i in range(self._preset_combo.count()):
                    if self._preset_combo.itemData(i) == target:
                        self._preset_combo.setCurrentIndex(i)
                        break
            elif ordered:
                self._preset_combo.setCurrentIndex(0)
        finally:
            self._suppress = False

        if self._preset_combo.count() > 0:
            # 兜底：suppress 期间的 setCurrentIndex 在某些 qfluentwidgets 版本
            # 下不会立即生效（内部还未 commit），导致 currentIndex() 返回 -1。
            # 这里如果发现没选中就再显式选一次，确保 _load_current_combo_entry
            # 能拿到合法 idx 并把 _current_preset_name 设上。
            if self._preset_combo.currentIndex() < 0:
                self._suppress = True
                try:
                    self._preset_combo.setCurrentIndex(0)
                finally:
                    self._suppress = False
            self._load_current_combo_entry()

    def _on_preset_combo_changed(self, _label: str) -> None:
        if self._suppress:
            return
        self._load_current_combo_entry()
        if self._current_preset_name:
            self._push_recent(self._current_preset_name)

    def _load_current_combo_entry(self) -> None:
        idx = self._preset_combo.currentIndex()
        if idx < 0:
            self._current_preset_name = None
            self._preset_status.setText("（未选择预设）")
            return
        name = self._preset_combo.itemData(idx)
        entry = next((e for e in self._entries if e.name == name), None)
        if entry is None:
            return
        self._current_preset_name = entry.name
        src_text = "系统" if entry.source is PresetSource.SYSTEM else "我的"
        self._preset_status.setText(f"来源：{src_text}（保存后将存为「我的」预设）")
        self._load_entry_into_form(entry.data)
        self.preset_changed.emit(self.current_preset_data())
        self.request_redraw_signal.emit()

    def _load_entry_into_form(self, data: dict[str, Any]) -> None:
        self._suppress = True
        try:
            self._id_column_edit.setText(str(data.get("id_column", "")))
            self._fname_edit.setText(str(data.get("filename_template", "")))
            self._title_edit.setText(str(data.get("title_template", "")))

            xa = data.get("x_axis") or {}
            ya = data.get("y_axis") or {}
            self._x_label_edit.setText(str(xa.get("label", "")))
            self._y_label_edit.setText(str(ya.get("label", "")))
            self._x_range.set_range(xa.get("range"))
            self._y_range.set_range(ya.get("range"))
            self._x_log_chk.setChecked(bool(xa.get("log", False)))
            self._y_log_chk.setChecked(bool(ya.get("log", False)))

            # P1.5-④ 次 Y 轴：data.y_axis2 为 None / 缺失 → 关闭
            y2 = data.get("y_axis2")
            y2_enabled = isinstance(y2, dict)
            self._y2_enable_chk.setChecked(y2_enabled)
            self._y2_fields_widget.setVisible(y2_enabled)
            if y2_enabled and isinstance(y2, dict):
                self._y2_label_edit.setText(str(y2.get("label", "")))
                self._y2_range.set_range(y2.get("range"))
                self._y2_log_chk.setChecked(bool(y2.get("log", False)))
            else:
                self._y2_label_edit.setText("")
                self._y2_range.set_range(None)
                self._y2_log_chk.setChecked(False)

            style = data.get("style") or {}
            self._show_grid_chk.setChecked(bool(style.get("grid", True)))
            legend_loc = style.get("legend")
            self._legend_combo.setCurrentText(legend_loc if legend_loc else "关闭")

            self._curves_editor.set_curves(data.get("curves") or [])
        finally:
            self._suppress = False

    def apply_preset_data(self, data: dict[str, Any]) -> None:
        """对外公共版的 _load_entry_into_form。

        P1.5-② 撤销/重做用：把 dict 数据反向写回 UI 字段，不触发 preset_changed
        信号（由 _suppress 标记保护），避免和 Undo 控制器形成回路。

        调用方需保证 data 是合法的"完整 preset 字典"（与 current_preset_data
        返回结构一致）。
        """
        self._load_entry_into_form(data)

    # ── 当前数据收集 ─────────────────────────────────────────────
    def current_preset_data(self) -> dict[str, Any]:
        # 图例位置：UI "关闭" → 不显示图例（legend=None）；其他原样
        legend_text = self._legend_combo.currentText()
        legend_loc = None if legend_text == "关闭" else legend_text
        # P1.5-④ 次 Y 轴：未启用 → y_axis2=None
        y_axis2: dict[str, Any] | None
        if self._y2_enable_chk.isChecked():
            y_axis2 = {
                "label": self._y2_label_edit.text(),
                "range": self._y2_range.get_range(),
                "log": self._y2_log_chk.isChecked(),
            }
        else:
            y_axis2 = None
        return {
            "id_column": self._id_column_edit.text().strip(),
            "filename_template": self._fname_edit.text(),
            "title_template": self._title_edit.text(),
            "x_axis": {
                "label": self._x_label_edit.text(),
                "range": self._x_range.get_range(),
                "log": self._x_log_chk.isChecked(),
            },
            "y_axis": {
                "label": self._y_label_edit.text(),
                "range": self._y_range.get_range(),
                "log": self._y_log_chk.isChecked(),
            },
            "y_axis2": y_axis2,
            "style": {
                "grid": self._show_grid_chk.isChecked(),
                "legend": legend_loc,
            },
            "curves": self._curves_editor.curves(),
        }

    def current_run_settings(self) -> PlotRunSettings:
        # 兜底：如果 _current_preset_name 由于初始化时序问题没同步上，
        # 直接从 ComboBox 当前选中项的 userData 取一次 —— 用户在 UI 上看到
        # ComboBox 已选中某条预设，行为上就该按"已选"处理，而不是回头逼用户再点一次。
        preset_name = self._current_preset_name
        if preset_name is None and self._preset_combo.count() > 0:
            idx = self._preset_combo.currentIndex()
            if idx < 0:
                idx = 0
            fallback = self._preset_combo.itemData(idx)
            if fallback:
                preset_name = str(fallback)
                # 顺手把内部状态修正，避免下一次又走 fallback
                self._current_preset_name = preset_name
        return PlotRunSettings(
            input_path=self._input_path,
            sheet_name=self._sheet_name,
            preset_name=preset_name,
            output_dir=self._output_dir,
            header_row=int(self._header_row_spin.value()),
        )

    # ── 数据源选择 ───────────────────────────────────────────────
    def _on_pick_input_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Excel 数据源",
            "",
            "Excel 文件 (*.xlsx *.xlsm)",
        )
        if not path:
            return
        self._input_path = Path(path)
        self._input_path_edit.setText(str(self._input_path))
        # 取该 Excel 的 sheet 名喂 ComboBox；用户随后可切
        self._refresh_sheet_combo()
        # 读 Excel 表头喂 CurvesEditor，让数据点 var_column 列从 LineEdit
        # 升级为 ComboBox（用户从下拉选 Excel 实际列名，避免手敲打错）
        self._refresh_excel_headers()
        self._emit_data_source_changed()

    def _refresh_sheet_combo(self) -> None:
        """根据当前 _input_path 读 sheet 名列表填充 ComboBox。失败兜底为 disabled。"""
        self._suppress = True
        try:
            self._sheet_combo.clear()
            if self._input_path is None or not self._input_path.is_file():
                self._sheet_combo.setEnabled(False)
                self._sheet_name = None
                return
            try:
                sheets = read_sheet_names(self._input_path)
            except ExcelReadError as e:
                log.warning("读取 sheet 名失败：%s", e)
                self._sheet_combo.setEnabled(False)
                self._sheet_name = None
                return
            if not sheets:
                self._sheet_combo.setEnabled(False)
                self._sheet_name = None
                return
            self._sheet_combo.addItems(sheets)
            self._sheet_combo.setEnabled(True)
            self._sheet_combo.setCurrentIndex(0)
            self._sheet_name = sheets[0]
        finally:
            self._suppress = False

    def _refresh_excel_headers(self) -> None:
        """读当前 Excel 表头并喂给 CurvesEditor，让数据点 var_column 列
        升级为 ComboBox 下拉（出 Excel 实际表头）。

        触发时机：Excel 路径 / sheet / 表头行号 任一变化。失败时静默清空，
        让 var_column 退化为 LineEdit（用户手敲列名）。
        """
        if self._input_path is None or not self._input_path.is_file():
            self._curves_editor.set_excel_headers(None)
            return
        try:
            headers = get_column_headers(
                self._input_path,
                self._sheet_name,
                header_row=int(self._header_row_spin.value()),
            )
        except ExcelReadError as e:
            log.warning("读取 Excel 表头失败：%s", e)
            self._curves_editor.set_excel_headers(None)
            return
        self._curves_editor.set_excel_headers(headers)

    def _on_pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", "")
        if path:
            self._output_dir = Path(path)
            self._output_dir_edit.setText(str(self._output_dir))

    # ── 预设按钮 ─────────────────────────────────────────────────
    def _on_new_preset(self) -> None:
        log.info("新建预设：清空表单")
        self._suppress = True
        try:
            self._current_preset_name = None
            self._preset_combo.setCurrentIndex(-1)
            self._preset_status.setText("新建预设（请填字段并点「保存为我的预设」）")
            self._load_entry_into_form(_EMPTY_PRESET_DATA)
        finally:
            self._suppress = False
        # bugfix: 默认 5 个内容分组都是收起态，用户点"+新建"看到的只是"清空"
        # 提示，看不到要填的字段位置。这里自动展开所有内容分组，让"哪儿能填什么"
        # 一目了然
        for sec in (
            self._sec_data,
            self._sec_curves,
            self._sec_axis,
            self._sec_style,
            self._sec_out,
        ):
            if not sec.is_expanded():
                sec._toggle()
        # 同时把焦点跳到第一个待填的输入框（Excel 路径），引导用户从"选数据源"开始
        self._input_path_edit.setFocus()
        self._emit_preset_changed()

    def _on_copy_preset(self) -> None:
        src = self._current_preset_name
        if not src:
            return
        new_name = self._ask_new_name(default=f"{src} 副本")
        if not new_name:
            return
        try:
            copy_system_to_user(src, new_name, tool="plot_curves")
        except PresetError as e:
            log.error("复制预设失败：%s", e)
            MessageBox("复制失败", str(e), self.window()).exec()
            return
        self.refresh(select_name=new_name)

    def _on_delete_preset(self) -> None:
        name = self._current_preset_name
        if not name:
            return
        entry = next((e for e in self._entries if e.name == name), None)
        if entry is None:
            return
        if entry.source is PresetSource.SYSTEM:
            MessageBox(
                "无法删除",
                f"「{name}」是系统预设，不能删除。\n"
                "如果想覆盖它，请改完字段后点「保存为我的预设」并保留同名。",
                self.window(),
            ).exec()
            return
        box = MessageBox(
            "删除预设",
            f"确认删除「我的」预设「{name}」？\n该操作不可撤销。",
            self.window(),
        )
        if not box.exec():
            return
        try:
            delete_user_preset(name, tool="plot_curves")
        except PresetError as e:
            log.error("删除预设失败：%s", e)
            MessageBox("删除失败", str(e), self.window()).exec()
            return
        self.refresh()

    def _on_save_preset(self) -> None:
        name = self._current_preset_name
        if not name:
            new_name = self._ask_new_name(default="新建预设")
            if not new_name:
                return
            name = new_name
        data = self.current_preset_data()
        try:
            save_user_preset(name, data, tool="plot_curves")
        except PresetError as e:
            log.error("保存预设失败：%s", e)
            MessageBox("保存失败", str(e), self.window()).exec()
            return
        log.info("已保存预设：%s", name)
        self.refresh(select_name=name)

    def _ask_new_name(self, default: str = "") -> str | None:
        from qfluentwidgets import MessageBoxBase

        class _NameDialog(MessageBoxBase):
            def __init__(self, parent_widget: QWidget) -> None:
                super().__init__(parent_widget)
                self.titleLabel = SubtitleLabel("输入预设名称", self)
                self.input_edit = LineEdit(self)
                self.input_edit.setText(default)
                self.input_edit.setPlaceholderText("不能为空，且不能以 _ 开头")
                self.viewLayout.addWidget(self.titleLabel)
                self.viewLayout.addWidget(self.input_edit)
                self.yesButton.setText("确定")
                self.cancelButton.setText("取消")

        dialog = _NameDialog(self.window())
        if not dialog.exec():
            return None
        text = dialog.input_edit.text().strip()
        if not text:
            return None
        if text.startswith("_"):
            MessageBox(
                "名称非法",
                "预设名称不能以下划线开头（保留给注释字段）。",
                self.window(),
            ).exec()
            return None
        return text

    # ── 最近使用持久化 ───────────────────────────────────────────
    def _make_settings(self) -> QSettings:
        return QSettings(_SETTINGS_ORG, _SETTINGS_APP)

    def _load_recent_names(self) -> list[str]:
        raw = self._make_settings().value(_SETTINGS_KEY_RECENT)
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        try:
            return [str(x) for x in raw][:_RECENT_PRESETS_MAX]
        except TypeError:
            return []

    def _push_recent(self, name: str) -> None:
        recent = self._load_recent_names()
        if name in recent:
            recent.remove(name)
        recent.insert(0, name)
        recent = recent[:_RECENT_PRESETS_MAX]
        self._make_settings().setValue(_SETTINGS_KEY_RECENT, recent)


__all__ = ["PresetAccordionPanel"]
