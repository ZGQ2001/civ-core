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

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
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
    SubtitleLabel,
    ToolButton,
)

from civ_core.domain.schema import PlotRunSettings
from civ_core.infra_io.excel_reader import ExcelReadError, read_sheet_names
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

# 新建预设的初始字段
_EMPTY_PRESET_DATA: dict[str, Any] = {
    "id_column": "编号",
    "filename_template": "{id}.png",
    "title_template": "{id}",
    "x_axis": {"label": "X", "range": None},
    "y_axis": {"label": "Y", "range": None},
    "curves": [],
}


# ──────────────────────────────────────────────────────────────────
# 私有控件
# ──────────────────────────────────────────────────────────────────
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

        # 标题栏：toggle 箭头 + 文字
        self._header = ToolButton(self)
        self._header.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._header.setText(self._title_text(title))
        self._header.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # 简洁的视觉：弱化分隔线，避免重边框
        self._header.setStyleSheet(
            "QToolButton { "
            "  text-align: left; "
            "  padding: 6px 8px; "
            "  font-weight: 600; "
            "  border: none; "
            "  border-bottom: 1px solid #e0e0e0; "
            "}"
            "QToolButton:hover { background: rgba(0,0,0,0.04); }"
        )
        if collapsible:
            self._header.clicked.connect(self._toggle)
        else:
            self._header.setEnabled(False)
        self._title = title
        outer.addWidget(self._header)

        # 内容容器
        self._body = QWidget(self)
        self._body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 6, 8, 8)
        self._body_layout.setSpacing(6)
        outer.addWidget(self._body)
        self._body.setVisible(initially_expanded)

    def _title_text(self, title: str) -> str:
        if not self._collapsible:
            return f"  {title}"
        arrow = "▾" if self._expanded else "▸"
        return f"{arrow}  {title}"

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._header.setText(self._title_text(self._title))

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
        self._slider.setRange(
            int(minimum * self._scale), int(maximum * self._scale)
        )
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
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer.addWidget(self._scroll)

        # 内容容器
        content = QWidget()
        content.setObjectName("presetAccordionContent")
        self._scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)  # 分组之间靠边框线分隔，不再加间距

        # 1. 预设选择（不可折叠）
        self._sec_preset = _CollapsibleSection(
            "预设选择", collapsible=False, parent=content
        )
        self._build_preset_section(self._sec_preset.body_layout())
        layout.addWidget(self._sec_preset)

        # 2. 数据源
        self._sec_data = _CollapsibleSection("数据源", parent=content)
        self._build_data_section(self._sec_data.body_layout())
        layout.addWidget(self._sec_data)

        # 3. 曲线定义（默认收起，避免初次开屏被巨大编辑器占满）
        self._sec_curves = _CollapsibleSection(
            "曲线定义", initially_expanded=False, parent=content
        )
        self._curves_editor = CurvesEditor(self)
        self._curves_editor.changed.connect(self._on_curves_changed)
        self._sec_curves.body_layout().addWidget(self._curves_editor)
        layout.addWidget(self._sec_curves)

        # 4. 坐标轴
        self._sec_axis = _CollapsibleSection(
            "坐标轴", initially_expanded=False, parent=content
        )
        self._build_axis_section(self._sec_axis.body_layout())
        layout.addWidget(self._sec_axis)

        # 5. 样式
        self._sec_style = _CollapsibleSection(
            "样式", initially_expanded=False, parent=content
        )
        self._build_style_section(self._sec_style.body_layout())
        layout.addWidget(self._sec_style)

        # 6. 输出
        self._sec_out = _CollapsibleSection(
            "输出", initially_expanded=False, parent=content
        )
        self._build_output_section(self._sec_out.body_layout())
        layout.addWidget(self._sec_out)

        # 末尾 stretch：分组全部折叠时把它们推到顶部，不会被外层均分
        layout.addStretch(1)

    # ── 1. 预设选择 ─────────────────────────────────────────────
    def _build_preset_section(self, layout: QVBoxLayout) -> None:
        self._preset_combo = ComboBox(self)
        self._preset_combo.currentTextChanged.connect(self._on_preset_combo_changed)
        layout.addWidget(self._preset_combo)

        self._preset_status = BodyLabel("", self)
        self._preset_status.setStyleSheet("color: #888;")
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
        layout.addLayout(
            _vertical_field("Excel 路径", self._input_path_edit, btn_browse_in)
        )

        # Sheet + 表头行号：一行两个字段（栅格 2 列）
        short_grid = QGridLayout()
        short_grid.setContentsMargins(0, 0, 0, 0)
        short_grid.setHorizontalSpacing(8)
        short_grid.setVerticalSpacing(2)

        short_grid.addWidget(BodyLabel("Sheet", self), 0, 0)
        self._sheet_combo = ComboBox(self)
        self._sheet_combo.setPlaceholderText("先选 Excel")
        self._sheet_combo.setEnabled(False)
        self._sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        short_grid.addWidget(self._sheet_combo, 1, 0)

        short_grid.addWidget(BodyLabel("表头行号", self), 0, 1)
        self._header_row_spin = SpinBox(self)
        self._header_row_spin.setRange(1, 50)
        self._header_row_spin.setValue(1)
        self._header_row_spin.valueChanged.connect(self._emit_request_redraw)
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
        layout.addLayout(
            _vertical_field("输出目录", self._output_dir_edit, btn_browse_out)
        )

    # ── 4. 坐标轴 ────────────────────────────────────────────────
    def _build_axis_section(self, layout: QVBoxLayout) -> None:
        # X / Y 各自一组：标签独占一行 + range 控件独占一行
        # （避免被横向挤到不可读）
        layout.addLayout(self._build_axis_block(axis="X"))
        layout.addLayout(self._build_axis_block(axis="Y"))

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

    # ── 5. 样式 ──────────────────────────────────────────────────
    def _build_style_section(self, layout: QVBoxLayout) -> None:
        self._show_grid_chk = CheckBox("显示网格", self)
        self._show_grid_chk.setChecked(True)
        self._show_grid_chk.stateChanged.connect(self._emit_request_redraw)
        layout.addWidget(self._show_grid_chk)

        layout.addWidget(BodyLabel("图例位置", self))
        self._legend_combo = ComboBox(self)
        self._legend_combo.addItems(["关闭"] + list(_LEGEND_LOC_CHOICES))
        self._legend_combo.setCurrentText("关闭")
        self._legend_combo.currentTextChanged.connect(self._emit_request_redraw)
        layout.addWidget(self._legend_combo)

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

    def _on_sheet_changed(self, sheet: str) -> None:
        if self._suppress:
            return
        self._sheet_name = sheet or None
        self._emit_data_source_changed()

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
        self._preset_status.setText(
            f"来源：{src_text}（保存后将存为「我的」预设）"
        )
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

            self._curves_editor.set_curves(data.get("curves") or [])
        finally:
            self._suppress = False

    # ── 当前数据收集 ─────────────────────────────────────────────
    def current_preset_data(self) -> dict[str, Any]:
        return {
            "id_column": self._id_column_edit.text().strip(),
            "filename_template": self._fname_edit.text(),
            "title_template": self._title_edit.text(),
            "x_axis": {
                "label": self._x_label_edit.text(),
                "range": self._x_range.get_range(),
            },
            "y_axis": {
                "label": self._y_label_edit.text(),
                "range": self._y_range.get_range(),
            },
            "curves": self._curves_editor.curves(),
        }

    def current_run_settings(self) -> PlotRunSettings:
        return PlotRunSettings(
            input_path=self._input_path,
            sheet_name=self._sheet_name,
            preset_name=self._current_preset_name,
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
