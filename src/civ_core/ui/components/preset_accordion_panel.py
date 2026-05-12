"""预设风琴参数面板（L-3b 实装）。

布局
====
六个自上而下的分组（首项不可折叠，其余可折叠）：
  1. 预设选择     —— 永远置顶；ComboBox + [+/复制/删除/保存]
  2. 数据源       —— Excel 路径 / 表头行号 / 输出目录
  3. 曲线定义     —— 装 L-3a 的 CurvesEditor
  4. 坐标轴       —— X/Y 轴标签 + range (min/max/step)
  5. 样式         —— 网格 + 图例位置
  6. 输出         —— filename_template / title_template / DPI / id_column

接口
====
  • preset_changed         Signal(dict)            预设字段全集改变
  • data_source_changed    Signal(object)          Excel 路径 (Path | None)
  • request_redraw_signal  Signal()                参数面板任意变化（view 用来防抖驱动 LivePreviewPane）
  • current_preset_data()  → dict                  当前预设字段（含 curves）
  • current_run_settings() → PlotRunSettings       当前运行时配置
  • refresh()                                       重新加载预设列表（写入后用）

"最近使用预设"
==============
QSettings 键 `plot_curves/recent_presets` 存最近 5 个预设名（按时间倒序）。
ComboBox 把这些项加到列表最前并以「★」前缀标识。

CLAUDE.md 合规
==============
  • 业务/IO/UI 分离：预设读取/保存调 preset_manager；本类只做 UI 显示和信号路由
  • 删除二次确认走 qfluentwidgets.MessageBox（视觉一致）
  • 数值字段尽量用 DoubleSpinBox；DPI 用 _SliderInputRow（合理范围有滑块意义）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
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
# 私有控件：可折叠分组 / 滑块+输入框
# ──────────────────────────────────────────────────────────────────
class _CollapsibleSection(QWidget):
    """简单的可折叠分组：标题栏点击 → 展开/收起内容。

    为什么自己写而不是用 QToolBox：
      • QToolBox 一次只能展开一个 page，6 个分组用户切来切去不便
      • qfluentwidgets 的 ExpandGroupSettingCard 面向"设置卡"，字段差异大不适合
      • 自写控件 ~50 行，按需展开关、保存折叠状态都好控制
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 标题栏：toggle 箭头 + 文字
        self._header = ToolButton(self)
        self._header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._header.setText(self._title_text(title))
        self._header.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._header.setStyleSheet(
            "QToolButton { text-align: left; padding: 4px 8px; font-weight: 600; }"
        )
        if collapsible:
            self._header.clicked.connect(self._toggle)
        else:
            self._header.setEnabled(False)  # 视觉上还在，禁用点击
        self._title = title
        outer.addWidget(self._header)

        # 内容容器
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 4, 4, 8)
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
        """对外暴露内容区 layout，让分组主体往里塞控件。"""
        return self._body_layout


class _SliderInputRow(QWidget):
    """滑块 + DoubleSpinBox 双向联动控件。

    场景：合理范围已知的数值字段（DPI / 线宽 / 标记尺寸等）。
    范围外的字段（轴 min/max）不适用 —— 那种直接用 DoubleSpinBox。
    """

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
        # Slider 走整数空间；与 DoubleSpinBox 用 _scale 做转换
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

        # 双向联动：用 blockSignals 防止递归
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

    未启用时输出 None；启用时输出 (min, max, step) 三元组。
    """

    valueChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._enable = CheckBox("启用固定范围", self)
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._enable)
        layout.addWidget(BodyLabel("min:", self))
        layout.addWidget(self._min)
        layout.addWidget(BodyLabel("max:", self))
        layout.addWidget(self._max)
        layout.addWidget(BodyLabel("step:", self))
        layout.addWidget(self._step)

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
        # rng 至少 3 个值
        if len(rng) >= 1:
            self._min.setValue(float(rng[0]))
        if len(rng) >= 2:
            self._max.setValue(float(rng[1]))
        if len(rng) >= 3:
            self._step.setValue(float(rng[2]))


# ──────────────────────────────────────────────────────────────────
# 主组件：PresetAccordionPanel
# ──────────────────────────────────────────────────────────────────
class PresetAccordionPanel(QWidget):
    """六分组风琴式参数面板。"""

    # 当前预设字段全集（含 curves）变化时发出 —— view 用来驱动 LivePreviewPane.set_preset
    preset_changed = Signal(dict)
    # Excel 数据源路径变化时发出 —— view 驱动 LivePreviewPane.set_data_source
    data_source_changed = Signal(object)
    # 任何字段变化都发一次 —— view 用来防抖触发 LivePreviewPane.request_redraw
    request_redraw_signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("presetAccordionPanel")

        # 内部状态
        self._entries: list[PresetEntry] = []  # 当前合并后的预设列表
        self._suppress: bool = False  # 程序性 setValue 时抑制信号
        # 当前预设名（与 ComboBox 选中项同步）
        self._current_preset_name: str | None = None

        # 运行时参数（不属于预设字段）
        self._input_path: Path | None = None
        self._output_dir: Path | None = None

        self._build_layout()
        self.refresh()

    # ── 顶层布局 ─────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # 1. 预设选择：不可折叠
        self._sec_preset = _CollapsibleSection(
            "预设选择", collapsible=False, parent=self
        )
        self._build_preset_section(self._sec_preset.body_layout())
        outer.addWidget(self._sec_preset)

        # 2. 数据源
        self._sec_data = _CollapsibleSection("数据源", parent=self)
        self._build_data_section(self._sec_data.body_layout())
        outer.addWidget(self._sec_data)

        # 3. 曲线定义（装 CurvesEditor）
        self._sec_curves = _CollapsibleSection("曲线定义", parent=self)
        self._curves_editor = CurvesEditor(self)
        self._curves_editor.changed.connect(self._on_curves_changed)
        self._sec_curves.body_layout().addWidget(self._curves_editor)
        outer.addWidget(self._sec_curves, 1)

        # 4. 坐标轴
        self._sec_axis = _CollapsibleSection(
            "坐标轴", initially_expanded=False, parent=self
        )
        self._build_axis_section(self._sec_axis.body_layout())
        outer.addWidget(self._sec_axis)

        # 5. 样式
        self._sec_style = _CollapsibleSection(
            "样式", initially_expanded=False, parent=self
        )
        self._build_style_section(self._sec_style.body_layout())
        outer.addWidget(self._sec_style)

        # 6. 输出
        self._sec_out = _CollapsibleSection(
            "输出", initially_expanded=False, parent=self
        )
        self._build_output_section(self._sec_out.body_layout())
        outer.addWidget(self._sec_out)

        outer.addStretch(0)  # 不让分组被拉得过散

    # ── 1. 预设选择 ─────────────────────────────────────────────
    def _build_preset_section(self, layout: QVBoxLayout) -> None:
        # ComboBox + 状态行
        self._preset_combo = ComboBox(self)
        self._preset_combo.currentTextChanged.connect(self._on_preset_combo_changed)
        layout.addWidget(self._preset_combo)

        self._preset_status = BodyLabel("", self)
        self._preset_status.setStyleSheet("color: #888;")
        layout.addWidget(self._preset_status)

        # 三按钮行：[+新建] [复制] [删除] [保存]
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
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
        self._btn_save = PrimaryPushButton("保存为我的预设", self)
        self._btn_save.clicked.connect(self._on_save_preset)
        btn_row.addWidget(self._btn_save)
        layout.addLayout(btn_row)

    # ── 2. 数据源 ────────────────────────────────────────────────
    def _build_data_section(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Excel 路径
        self._input_path_edit = LineEdit(self)
        self._input_path_edit.setPlaceholderText("点击右侧按钮选择 Excel")
        self._input_path_edit.setReadOnly(True)
        btn_browse_in = PushButton("选择…", self)
        btn_browse_in.clicked.connect(self._on_pick_input_excel)
        row_in = QHBoxLayout()
        row_in.addWidget(self._input_path_edit, 1)
        row_in.addWidget(btn_browse_in)
        form.addRow("Excel 路径:", row_in)

        # 表头行号
        self._header_row_spin = SpinBox(self)
        self._header_row_spin.setRange(1, 50)
        self._header_row_spin.setValue(1)
        self._header_row_spin.valueChanged.connect(self._emit_request_redraw)
        form.addRow("表头行号:", self._header_row_spin)

        # 输出目录（运行时配置）
        self._output_dir_edit = LineEdit(self)
        self._output_dir_edit.setPlaceholderText("点击右侧按钮选择输出目录")
        self._output_dir_edit.setReadOnly(True)
        btn_browse_out = PushButton("选择…", self)
        btn_browse_out.clicked.connect(self._on_pick_output_dir)
        row_out = QHBoxLayout()
        row_out.addWidget(self._output_dir_edit, 1)
        row_out.addWidget(btn_browse_out)
        form.addRow("输出目录:", row_out)

        layout.addLayout(form)

    # ── 4. 坐标轴 ────────────────────────────────────────────────
    def _build_axis_section(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._x_label_edit = LineEdit(self)
        self._x_label_edit.editingFinished.connect(self._on_axis_changed)
        form.addRow("X 标签:", self._x_label_edit)

        self._x_range = _RangeTrio(self)
        self._x_range.valueChanged.connect(self._on_axis_changed)
        form.addRow("X 范围:", self._x_range)

        self._y_label_edit = LineEdit(self)
        self._y_label_edit.editingFinished.connect(self._on_axis_changed)
        form.addRow("Y 标签:", self._y_label_edit)

        self._y_range = _RangeTrio(self)
        self._y_range.valueChanged.connect(self._on_axis_changed)
        form.addRow("Y 范围:", self._y_range)

        layout.addLayout(form)

    # ── 5. 样式 ──────────────────────────────────────────────────
    def _build_style_section(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._show_grid_chk = CheckBox("显示网格", self)
        self._show_grid_chk.setChecked(True)
        self._show_grid_chk.stateChanged.connect(self._emit_request_redraw)
        form.addRow("网格:", self._show_grid_chk)

        self._legend_combo = ComboBox(self)
        self._legend_combo.addItems(["关闭"] + list(_LEGEND_LOC_CHOICES))
        self._legend_combo.setCurrentText("关闭")
        self._legend_combo.currentTextChanged.connect(self._emit_request_redraw)
        form.addRow("图例位置:", self._legend_combo)

        layout.addLayout(form)

    # ── 6. 输出 ──────────────────────────────────────────────────
    def _build_output_section(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._id_column_edit = LineEdit(self)
        self._id_column_edit.setPlaceholderText("Excel 里作为「标识列」的列名")
        self._id_column_edit.editingFinished.connect(self._emit_preset_changed)
        form.addRow("标识列名:", self._id_column_edit)

        self._fname_edit = LineEdit(self)
        self._fname_edit.setPlaceholderText("如  锚杆{id}_曲线.png")
        self._fname_edit.editingFinished.connect(self._emit_preset_changed)
        form.addRow("文件名模板:", self._fname_edit)

        self._title_edit = LineEdit(self)
        self._title_edit.setPlaceholderText("如  锚杆{id}：曲线")
        self._title_edit.editingFinished.connect(self._emit_preset_changed)
        form.addRow("图标题模板:", self._title_edit)

        self._dpi_row = _SliderInputRow(
            minimum=50.0,
            maximum=400.0,
            step=10.0,
            decimals=0,
            initial=150.0,
            parent=self,
        )
        self._dpi_row.valueChanged.connect(self._emit_request_redraw)
        form.addRow("PNG DPI:", self._dpi_row)

        layout.addLayout(form)

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

    def _on_axis_changed(self) -> None:
        self._emit_preset_changed()

    def _on_curves_changed(self) -> None:
        self._emit_preset_changed()

    # ── 预设 ComboBox 交互 ───────────────────────────────────────
    def refresh(self, select_name: str | None = None) -> None:
        """重新从 preset_manager 加载预设；select_name 指定刷新后选中项。"""
        try:
            self._entries = load_merged_presets("plot_curves")
        except PresetError as e:
            log.error("加载预设失败：%s", e)
            self._entries = []

        # 重排：把最近使用的提到前面
        recent = self._load_recent_names()
        recent_set = set(recent)
        recent_in_list = [
            e for n in recent for e in self._entries if e.name == n
        ]
        rest = [e for e in self._entries if e.name not in recent_set]
        ordered = recent_in_list + rest

        # 喂 ComboBox
        self._suppress = True
        try:
            self._preset_combo.clear()
            for e in ordered:
                mark = "★ " if e.name in recent_set else ""
                self._preset_combo.addItem(f"{mark}{e.name}", userData=e.name)

            # 选中目标
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

        # 触发一次主动加载（即便 setCurrentIndex 没触发信号）
        if self._preset_combo.count() > 0:
            self._load_current_combo_entry()

    def _on_preset_combo_changed(self, _label: str) -> None:
        if self._suppress:
            return
        self._load_current_combo_entry()
        # 记录到最近使用
        if self._current_preset_name:
            self._push_recent(self._current_preset_name)

    def _load_current_combo_entry(self) -> None:
        """根据 ComboBox 当前 index 把对应 entry 加载到所有表单字段。"""
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
        # 触发 LivePreviewPane 重新加载
        self.preset_changed.emit(self.current_preset_data())
        self.request_redraw_signal.emit()

    def _load_entry_into_form(self, data: dict[str, Any]) -> None:
        """把预设 data 字段铺到各控件。suppress 期间所有 setValue 不发信号。"""
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
        """从控件聚合出预设字段 dict（与 curve_presets.json 单条预设结构一致）。"""
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
        """聚合 PlotRunSettings（运行时配置，不属于预设）。"""
        return PlotRunSettings(
            input_path=self._input_path,
            sheet_name=None,
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
        if path:
            self._input_path = Path(path)
            self._input_path_edit.setText(str(self._input_path))
            self.data_source_changed.emit(self._input_path)
            self._emit_request_redraw()

    def _on_pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", "")
        if path:
            self._output_dir = Path(path)
            self._output_dir_edit.setText(str(self._output_dir))

    # ── 预设按钮：新建 / 复制 / 删除 / 保存 ──────────────────────
    def _on_new_preset(self) -> None:
        # 新建：本地 form 清空 + 留待保存
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
        """复制当前选中预设 → 弹输名对话框 → 走 preset_manager.copy_system_to_user。"""
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
        # 同名系统预设可能恢复 → 刷新列表
        self.refresh()

    def _on_save_preset(self) -> None:
        """保存当前 form → 走 preset_manager.save_user_preset。"""
        name = self._current_preset_name
        if not name:
            # 新建态需要先问名字
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
        """简单的"输入名字"对话框：用 MessageBox + LineEdit 模拟。

        qfluentwidgets 没有直接的 InputDialog；这里用一个 MessageBox 子集，
        把 contentLabel 替换成 LineEdit 即可。
        """
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
        """读 QSettings 中最近使用的预设名列表（容错）。"""
        raw = self._make_settings().value(_SETTINGS_KEY_RECENT)
        if raw is None:
            return []
        if isinstance(raw, str):
            # 单值兜底：QSettings INI 后端在单条目时可能存成 str
            return [raw]
        try:
            return [str(x) for x in raw][:_RECENT_PRESETS_MAX]
        except TypeError:
            return []

    def _push_recent(self, name: str) -> None:
        """把 name 推到最近使用列表头部。"""
        recent = self._load_recent_names()
        if name in recent:
            recent.remove(name)
        recent.insert(0, name)
        recent = recent[:_RECENT_PRESETS_MAX]
        self._make_settings().setValue(_SETTINGS_KEY_RECENT, recent)


__all__ = ["PresetAccordionPanel"]
