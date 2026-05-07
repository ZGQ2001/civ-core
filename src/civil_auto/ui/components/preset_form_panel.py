"""绘曲线图工具的「预设设置」表单子面板（中栏 Pivot 第二个 Tab 的内容）。

职责
====
  • 把一条 PresetEntry 的内部字段铺到表单上，让用户可视化地查看 / 编辑
  • 维护 dirty 状态：当前表单内容相对 set_entry 时的 baseline 是否有变更
  • 通过 set_read_only(bool) 一次切换全部控件的可编辑性（系统预设 → 只读）
  • 不直接调写入 API：调用方在「保存修改」时拿 current_data() 喂 preset_manager

字段映射（与 presets/plot_curves/curve_presets.json 顶层 schema 一致）
========================================================================
  name              : 顶部 LineEdit（不在 data 里，但是 dict key）
  id_column         : LineEdit
  filename_template : LineEdit（说明 {id} 占位符）
  title_template    : LineEdit（同上）
  x_axis.label      : LineEdit
  x_axis.range      : 「自动」CheckBox + (min, max, step) 三个 DoubleSpinBox
  y_axis.label      : LineEdit
  y_axis.range      : 同上
  curves            : 多行 JSON PlainTextEdit（本轮先做"半结构化"——文本编辑 + 解析时校验）

为什么 curves 用 JSON 文本框
==============================
curves 是 list[dict]，里面又嵌套 points list（fixed_axis / fixed_value / var_column 等），
做完整 GUI 编辑器 = 02_Core/curve_template_editor.py 那一整套迁移工作量。
本轮 T-4 时间预算优先级低于"中栏 Pivot 双 Tab 跑通"，所以先用 JSON 文本框：
  • 系统预设：只读看 JSON 已经够用
  • 用户预设：用户改简单字段（color/marker/linewidth）走文本编辑没什么阻碍
  • curves 完整 GUI 编辑器留 P1「预设编辑器迁移」单独做

设计取舍
========
  • 不在表单里强制实时校验（比如 range 三个 spin 是否单调递增）—— 实时校验会给 UI
    带来很多 InfoBar 噪音；改在「保存修改」按钮上做一次性校验（Step 5 实现）
  • dirty 信号是相对 baseline（set_entry 时的快照）的"内容差异"，不是"用户敲过键盘"。
    用户敲完又改回原样 → dirty 自动消失，UI 上保存按钮跟着禁用，符合直觉
  • 默认值与表单空值的处理：set_entry(None) 把所有字段清空，用于「+新建」场景
"""

from __future__ import annotations

import copy
import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    DoubleSpinBox,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
)

from civil_auto.infra_io.preset_manager import PresetEntry
from civil_auto.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 范围三元组子组件（[min, max, step] / null）
# ──────────────────────────────────────────────────────────────────
class _RangeRow(QWidget):
    """一行"轴范围"：[ ✓ 自动 ] [min] [max] [step]。

    - "自动"勾上 → 三个 spin 禁用 + 灰色，对外的 range_value() 返回 None
    - "自动"取消 → 三个 spin 启用，range_value() 返回 [min, max, step]
    - 任何子控件变化都 emit changed()，由父级聚合到 dirty 检测
    """

    changed = Signal()

    # SpinBox 范围足够覆盖典型工程量（位移 mm、荷载 kN、回弹值等）。
    # 不限制更宽是为了避免用户碰到边界报错；想真正越界基本要靠手敲 JSON。
    _SPIN_MIN = -1.0e6
    _SPIN_MAX = 1.0e6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.auto_cb = CheckBox("自动", self)
        self.auto_cb.setToolTip("勾上 = 让 matplotlib 自动决定该轴的刻度范围（JSON 写 null）")
        self.auto_cb.toggled.connect(self._on_auto_toggled)
        self.auto_cb.toggled.connect(self.changed)
        layout.addWidget(self.auto_cb)

        self.min_spin = self._make_spin("最小值")
        self.max_spin = self._make_spin("最大值")
        self.step_spin = self._make_spin("步长")
        for w, label in [
            (self.min_spin, "min"),
            (self.max_spin, "max"),
            (self.step_spin, "step"),
        ]:
            layout.addWidget(BodyLabel(label, self))
            layout.addWidget(w)

        layout.addStretch(1)

    def _make_spin(self, tooltip: str) -> DoubleSpinBox:
        s = DoubleSpinBox(self)
        s.setRange(self._SPIN_MIN, self._SPIN_MAX)
        s.setDecimals(2)
        s.setSingleStep(1.0)
        s.setMinimumWidth(90)
        s.setToolTip(tooltip)
        s.valueChanged.connect(self.changed)
        return s

    def _on_auto_toggled(self, checked: bool) -> None:
        self.min_spin.setEnabled(not checked)
        self.max_spin.setEnabled(not checked)
        self.step_spin.setEnabled(not checked)

    # ── 公共 API ──────────────────────────────────────────────────
    def set_value(self, value: list[float] | None) -> None:
        """把 JSON 的 range 值（None 或 [min, max, step]）推进 UI。

        block 信号，避免初始化时一连串 valueChanged 把 dirty 搞乱。
        """
        self.auto_cb.blockSignals(True)
        self.min_spin.blockSignals(True)
        self.max_spin.blockSignals(True)
        self.step_spin.blockSignals(True)
        try:
            if value is None:
                self.auto_cb.setChecked(True)
                # 三个 spin 不动，禁用即可
                self._on_auto_toggled(True)
            else:
                # 容错：少于 3 个值时 missing 元素填 0；多于 3 个的尾巴扔掉
                vs = list(value) + [0.0] * (3 - len(value))
                self.auto_cb.setChecked(False)
                self.min_spin.setValue(float(vs[0]))
                self.max_spin.setValue(float(vs[1]))
                self.step_spin.setValue(float(vs[2]))
                self._on_auto_toggled(False)
        finally:
            self.auto_cb.blockSignals(False)
            self.min_spin.blockSignals(False)
            self.max_spin.blockSignals(False)
            self.step_spin.blockSignals(False)

    def value(self) -> list[float] | None:
        """读出当前 UI → JSON range 值。"""
        if self.auto_cb.isChecked():
            return None
        return [
            self.min_spin.value(),
            self.max_spin.value(),
            self.step_spin.value(),
        ]

    def set_read_only(self, read_only: bool) -> None:
        # CheckBox + 三个 SpinBox 一并切只读
        self.auto_cb.setEnabled(not read_only)
        # spin 是否启用还要受 auto 影响：read_only=True 时全部禁用；
        # read_only=False 时由 _on_auto_toggled 负责
        if read_only:
            self.min_spin.setEnabled(False)
            self.max_spin.setEnabled(False)
            self.step_spin.setEnabled(False)
        else:
            self._on_auto_toggled(self.auto_cb.isChecked())


# ──────────────────────────────────────────────────────────────────
# 主面板
# ──────────────────────────────────────────────────────────────────
class PresetFormPanel(ScrollArea):
    """「预设设置」表单子面板。

    Signals:
      dirty_changed(bool)
        当 dirty 状态翻转时 emit。dirty 的判定标准是
        "current_data + name 与 baseline 不一致"，所以用户改完又改回去
        会自动恢复 dirty=False。
      copy_to_user_requested()
        系统预设态下点击 [复制为我的预设] 按钮时 emit。view 接到后
        转发给左栏 PresetListPane._on_copy_clicked() 流程。
      save_requested()
        用户预设态 / 新建态下点击 [保存修改] / [保存为我的预设] 时 emit。
        view 接到后做字段校验 + 调 save_user_preset。
      reset_requested()
        用户预设态下点击 [重置] 时 emit。view 接到后回调 form.reset_to_baseline()。
        （没让 form 自己处理是为了让"重置"语义集中在 view 层，便于扩展二次确认。）
      cancel_new_requested()
        新建态下点击 [取消] 时 emit。view 接到后让左栏选回首项 + 切回非新建态。

    Public API:
      .set_entry(entry: PresetEntry | None)
        把一条预设推进表单。entry=None 表示"清空"（用于"+新建"场景）。
      .current_name() -> str
        当前 name 文本框值（去除前后空白）
      .current_data() -> dict
        当前表单 → JSON 字典（不含 name）。curves 字段在这里做一次 JSON 解析；
        解析失败返回时仍带 curves 键，但 value 是 list with one error placeholder
        —— 由调用方在保存前再校验一次。这里不抛，避免读字段时炸。
      .current_curves_text() -> str
        curves PlainTextEdit 的原始文本。供保存校验时拿到准确报错位置。
      .set_read_only(read_only: bool)
        系统预设 → True；用户预设 / 新建 → False
        切换时同步刷新底部按钮区显示（系统/用户/新建三态）。
      .is_dirty() -> bool
      .reset_to_baseline()
        把表单恢复到 baseline（最后一次 set_entry 时的快照），用于"重置"按钮
      .baseline_name() -> str
        最近一次 set_entry 时记录的 name；空字符串 = 新建态（baseline 没有起源条目）
    """

    dirty_changed = Signal(bool)
    copy_to_user_requested = Signal()
    save_requested = Signal()
    reset_requested = Signal()
    cancel_new_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("presetFormPanel")

        # baseline = 上次 set_entry 时落下来的"原始"快照，用于 dirty 比较 / reset。
        # 包含 name + data 两部分，方便 reset_to_baseline 一把推回去。
        self._baseline_name: str = ""
        self._baseline_data: dict[str, Any] = {}
        self._dirty: bool = False
        self._read_only: bool = False

        self._build_ui()
        self._wire_signals()
        log.debug("PresetFormPanel ready")

    # ── 构造 ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget(self)
        content.setObjectName("presetFormContent")
        content.setStyleSheet(
            "QWidget#presetFormContent { background: transparent; }"
        )
        self.setWidget(content)

        outer = QVBoxLayout(content)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # ── 顶部说明（说明当前来源 / 编辑提示）──
        self._hint_label = BodyLabel("（请从左栏选择预设，或点 [+新建]）", content)
        self._hint_label.setStyleSheet("color: #888;")
        self._hint_label.setWordWrap(True)
        outer.addWidget(self._hint_label)

        # ── 顶层字段 ──
        outer.addWidget(SubtitleLabel("基本信息", content))
        form_basic = QFormLayout()
        form_basic.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_basic.setHorizontalSpacing(12)
        form_basic.setVerticalSpacing(8)

        self.name_edit = LineEdit(content)
        self.name_edit.setPlaceholderText("预设名称（在合并列表里作为唯一 key）")
        form_basic.addRow(StrongBodyLabel("预设名称", content), self.name_edit)

        self.id_column_edit = LineEdit(content)
        self.id_column_edit.setPlaceholderText("Excel 中作为每行标识的列名")
        form_basic.addRow(StrongBodyLabel("标识列", content), self.id_column_edit)

        self.filename_template_edit = LineEdit(content)
        self.filename_template_edit.setPlaceholderText("如：锚杆{id}_荷载位移曲线.png")
        form_basic.addRow(
            StrongBodyLabel("文件名模板", content), self.filename_template_edit
        )

        self.title_template_edit = LineEdit(content)
        self.title_template_edit.setPlaceholderText("如：锚杆{id}：荷载-位移曲线")
        form_basic.addRow(
            StrongBodyLabel("图标题模板", content), self.title_template_edit
        )

        outer.addLayout(form_basic)

        # ── X 轴 ──
        outer.addWidget(SubtitleLabel("X 轴", content))
        form_x = QFormLayout()
        form_x.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_x.setHorizontalSpacing(12)
        form_x.setVerticalSpacing(8)

        self.x_label_edit = LineEdit(content)
        self.x_label_edit.setPlaceholderText("如：位移 (mm)")
        form_x.addRow(StrongBodyLabel("X 轴标签", content), self.x_label_edit)

        self.x_range_row = _RangeRow(content)
        form_x.addRow(StrongBodyLabel("X 轴范围", content), self.x_range_row)

        outer.addLayout(form_x)

        # ── Y 轴 ──
        outer.addWidget(SubtitleLabel("Y 轴", content))
        form_y = QFormLayout()
        form_y.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_y.setHorizontalSpacing(12)
        form_y.setVerticalSpacing(8)

        self.y_label_edit = LineEdit(content)
        self.y_label_edit.setPlaceholderText("如：荷载 (KN)")
        form_y.addRow(StrongBodyLabel("Y 轴标签", content), self.y_label_edit)

        self.y_range_row = _RangeRow(content)
        form_y.addRow(StrongBodyLabel("Y 轴范围", content), self.y_range_row)

        outer.addLayout(form_y)

        # ── 曲线（curves）—— JSON 多行编辑 ──
        outer.addWidget(SubtitleLabel("曲线（curves）", content))
        curves_hint = BodyLabel(
            "本字段结构复杂（颜色/标记/点序列），暂以 JSON 形式编辑；"
            "完整可视化编辑器后续版本提供。",
            content,
        )
        curves_hint.setStyleSheet("color: #888;")
        curves_hint.setWordWrap(True)
        outer.addWidget(curves_hint)

        self.curves_edit = PlainTextEdit(content)
        self.curves_edit.setPlaceholderText(
            '示例：[{"name": "加载", "color": "#1F4FE0", "marker": "s", "linewidth": 2, '
            '"markersize": 7, "points": [...]}]'
        )
        # 等宽字体看 JSON 更舒服
        font = self.curves_edit.font()
        font.setFamily("Consolas")
        self.curves_edit.setFont(font)
        self.curves_edit.setMinimumHeight(180)
        outer.addWidget(self.curves_edit)

        outer.addStretch(1)

        # ── 底部按钮区：按当前模式（系统/用户/新建）显示不同按钮 ──
        # 三个按钮共存，靠 setVisible 切换；统一占一行，避免布局抖动
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 8, 0, 0)
        btn_row.addStretch(1)  # 按钮靠右

        # 系统预设态
        self._copy_btn = PrimaryPushButton("复制为我的预设", content)
        self._copy_btn.setToolTip("系统预设不能直接修改；复制为我的预设后才能编辑")
        self._copy_btn.clicked.connect(self.copy_to_user_requested)
        btn_row.addWidget(self._copy_btn)

        # 用户预设态 / 新建态共用 [保存修改 / 保存为我的预设]
        # 文字按模式动态切换，按钮对象只一个
        self._save_btn = PrimaryPushButton("保存修改", content)
        self._save_btn.clicked.connect(self.save_requested)
        btn_row.addWidget(self._save_btn)

        # 用户预设态
        self._reset_btn = PushButton("重置", content)
        self._reset_btn.setToolTip("把字段恢复到加载时的原值")
        self._reset_btn.clicked.connect(self.reset_requested)
        btn_row.addWidget(self._reset_btn)

        # 新建态
        self._cancel_btn = PushButton("取消", content)
        self._cancel_btn.setToolTip("放弃新建，回到默认预设")
        self._cancel_btn.clicked.connect(self.cancel_new_requested)
        btn_row.addWidget(self._cancel_btn)

        outer.addLayout(btn_row)
        # 初始：未 set_entry 之前，所有按钮都隐藏（"请从左栏选择"提示）
        self._copy_btn.hide()
        self._save_btn.hide()
        self._reset_btn.hide()
        self._cancel_btn.hide()

    def _wire_signals(self) -> None:
        # 任意字段变化 → 重新计算 dirty
        self.name_edit.textChanged.connect(self._recompute_dirty)
        self.id_column_edit.textChanged.connect(self._recompute_dirty)
        self.filename_template_edit.textChanged.connect(self._recompute_dirty)
        self.title_template_edit.textChanged.connect(self._recompute_dirty)
        self.x_label_edit.textChanged.connect(self._recompute_dirty)
        self.y_label_edit.textChanged.connect(self._recompute_dirty)
        self.x_range_row.changed.connect(self._recompute_dirty)
        self.y_range_row.changed.connect(self._recompute_dirty)
        self.curves_edit.textChanged.connect(self._recompute_dirty)

    # ── 公共 API ──────────────────────────────────────────────────
    def set_entry(self, entry: PresetEntry | None) -> None:
        """把一条预设推进表单。entry=None → 清空（"+新建"场景）。

        进来时整段 block 信号，避免逐字段写入触发 N 次 dirty 重算。
        最后统一刷一次 baseline + dirty=False，再刷一次按钮可见性。
        """
        if entry is None:
            name = ""
            data: dict[str, Any] = {}
        else:
            name = entry.name
            data = copy.deepcopy(entry.data)  # 防外部 mutate 影响 baseline

        self._set_all_blocked(name, data)

        # baseline 用深拷贝，防外面改 entry 影响比较结果
        self._baseline_name = name
        self._baseline_data = copy.deepcopy(data)
        self._set_dirty(False)

        # 顶部 hint 文字根据是否有 entry 切换
        if entry is None:
            self._hint_label.setText("（新建预设：填好字段后点「保存为我的预设」落盘）")
        else:
            self._hint_label.setText(
                f"当前预设：{entry.name}（{'系统预设（只读）' if entry.source.value == 'system' else '我的预设'}）"
            )

        # 模式切换可能改了按钮区显示
        self._update_button_visibility()

    def current_name(self) -> str:
        return self.name_edit.text().strip()

    def current_data(self) -> dict[str, Any]:
        """从 UI 读出当前 data dict（不含 name）。

        curves 字段处理：
          - 文本框为空 → curves = []（合理默认；保存校验时再说要不要拒绝空）
          - 文本框是合法 JSON 且解析为 list → 直接用
          - 解析失败 → 把"错"塞进结果里（curves = [{"_parse_error": ..., "_raw": ...}]），
            让保存时的校验能识别到，进而提示用户。
            不抛异常的原因：current_data 是被多处轻量调用的（dirty 计算等），
            一调就抛会让无关功能崩溃。
        """
        return {
            "id_column": self.id_column_edit.text(),
            "filename_template": self.filename_template_edit.text(),
            "title_template": self.title_template_edit.text(),
            "x_axis": {
                "label": self.x_label_edit.text(),
                "range": self.x_range_row.value(),
            },
            "y_axis": {
                "label": self.y_label_edit.text(),
                "range": self.y_range_row.value(),
            },
            "curves": self._parse_curves_lenient(),
        }

    def current_curves_text(self) -> str:
        """供"保存校验"时拿到 JSON 原文做精准报错（行号 / 列号）。"""
        return self.curves_edit.toPlainText()

    def set_read_only(self, read_only: bool) -> None:
        """切换全表单的可编辑性。系统预设进来 → True；用户预设 → False。

        切完同步刷一次按钮可见性（因为按钮态依赖 read_only）。
        """
        self._read_only = read_only
        for w in (
            self.name_edit,
            self.id_column_edit,
            self.filename_template_edit,
            self.title_template_edit,
            self.x_label_edit,
            self.y_label_edit,
        ):
            w.setReadOnly(read_only)
        self.curves_edit.setReadOnly(read_only)
        self.x_range_row.set_read_only(read_only)
        self.y_range_row.set_read_only(read_only)
        self._update_button_visibility()

    def is_dirty(self) -> bool:
        return self._dirty

    def baseline_name(self) -> str:
        """最近一次 set_entry 落下的 name（空字符串 = 新建态）。"""
        return self._baseline_name

    def reset_to_baseline(self) -> None:
        """把表单恢复到 baseline（"重置"按钮）。"""
        self._set_all_blocked(self._baseline_name, self._baseline_data)
        self._set_dirty(False)

    # ── 内部 ──────────────────────────────────────────────────────
    def _set_all_blocked(self, name: str, data: dict[str, Any]) -> None:
        """无信号地把字段全部刷到 UI。block 一次，写完再恢复，最后手动算一次 dirty。"""
        widgets = [
            self.name_edit,
            self.id_column_edit,
            self.filename_template_edit,
            self.title_template_edit,
            self.x_label_edit,
            self.y_label_edit,
            self.curves_edit,
        ]
        for w in widgets:
            w.blockSignals(True)
        try:
            self.name_edit.setText(name)
            self.id_column_edit.setText(str(data.get("id_column", "")))
            self.filename_template_edit.setText(
                str(data.get("filename_template", ""))
            )
            self.title_template_edit.setText(
                str(data.get("title_template", ""))
            )

            x_axis = data.get("x_axis") or {}
            self.x_label_edit.setText(str(x_axis.get("label", "")))
            self.x_range_row.set_value(x_axis.get("range"))

            y_axis = data.get("y_axis") or {}
            self.y_label_edit.setText(str(y_axis.get("label", "")))
            self.y_range_row.set_value(y_axis.get("range"))

            # curves 用 indent JSON 落到文本框，方便用户读
            curves = data.get("curves", [])
            self.curves_edit.setPlainText(
                json.dumps(curves, indent=2, ensure_ascii=False)
            )
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _parse_curves_lenient(self) -> list[dict[str, Any]]:
        """解析 curves 文本框；失败时返回带错误标记的占位 list。"""
        text = self.curves_edit.toPlainText().strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            return [{"_parse_error": str(e), "_raw": text}]

        if not isinstance(parsed, list):
            return [
                {
                    "_parse_error": f"curves 顶层应为 list，实得 {type(parsed).__name__}",
                    "_raw": text,
                }
            ]
        return parsed

    def _recompute_dirty(self) -> None:
        """与 baseline 比较，更新 dirty 状态（必要时 emit）。"""
        cur_name = self.current_name()
        cur_data = self.current_data()

        is_dirty = (
            cur_name != self._baseline_name or cur_data != self._baseline_data
        )
        self._set_dirty(is_dirty)

    def _set_dirty(self, value: bool) -> None:
        if value != self._dirty:
            self._dirty = value
            self.dirty_changed.emit(value)
        # 不管翻不翻转，都刷一次"保存"按钮启用 —— 这样只有 dirty 时保存才能点
        self._update_save_enabled()

    def _update_button_visibility(self) -> None:
        """按当前模式（系统/用户/新建）切换底部按钮区显示。

        模式判定：
          • read_only=True              → 系统预设态，单按钮 [复制为我的预设]
          • read_only=False, baseline_name=""    → 新建态 [保存为我的预设] [取消]
          • read_only=False, baseline_name 非空 → 用户预设态 [保存修改] [重置]
        """
        is_new_draft = (not self._read_only) and (self._baseline_name == "")
        is_system = self._read_only
        is_user_edit = (not self._read_only) and (self._baseline_name != "")

        self._copy_btn.setVisible(is_system)
        self._save_btn.setVisible(is_new_draft or is_user_edit)
        self._reset_btn.setVisible(is_user_edit)
        self._cancel_btn.setVisible(is_new_draft)

        # 文字按模式切，让用户看清"是覆盖原条目还是新建一条"
        if is_new_draft:
            self._save_btn.setText("保存为我的预设")
        else:
            self._save_btn.setText("保存修改")

        self._update_save_enabled()

    def _update_save_enabled(self) -> None:
        """保存按钮的启用：只有 dirty 状态下才能保存（避免无意义的写盘）。

        新建态 baseline 是空，set_entry(None) 后任何输入都会让 dirty=True，
        所以在新建态下 dirty=False 意味着用户什么都没填，自然不让保存。
        """
        self._save_btn.setEnabled(self._dirty)
