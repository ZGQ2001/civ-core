"""曲线可视化编辑器（L-3a，吸收原"预设编辑器迁移"任务）。

参考实现：old_code/02_Core/curve_template_editor.py（tkinter 673 行）
本模块只迁移"曲线列表 + 选中曲线字段 + 点序列子表"那一段；模板列表/复制/删除
归 L-3b 的"预设选择"分组。

业务字段（与 curve_presets.json 单条预设里的 curves 项一致）：
  • name        : str
  • color       : "#RRGGBB"
  • marker      : "s" / "o" / "^" / "v" / "D" / "x" / "*" / "+"
  • linewidth   : float (> 0)
  • markersize  : float (>= 0)
  • points      : list[{fixed_axis, fixed_value, var_column}]

接口
====
  • set_curves(curves)            —— 喂初始 curves 列表（深拷贝持有，外部不污染）
  • curves() -> list[dict]        —— 取当前编辑结果
  • set_excel_headers(headers)    —— 挂 Excel 表头，var_column 退化 LineEdit → ComboBox
  • changed = Signal()            —— 任意字段编辑后发射一次（防抖在 view 层做）

设计选择
========
  • 编辑器自己持有 list[dict] 副本 —— 调用方 set 时深拷贝传入；外部即使后续
    mutate 也不影响编辑器；调用方拿 curves() 时也返回深拷贝
  • 点表用 QTableWidget + cellWidget：每行三个 cell（QComboBox + QDoubleSpinBox
    + QComboBox/QLineEdit）—— 不用 Model/View（点数通常 <10，QTableWidget 够用且 API 简单）
  • 曲线列表横向：左侧 QListWidget + 右侧"+/复制/删除/↑/↓"竖排按钮组
  • 颜色：6 个快选按钮 + "更多颜色…" 弹 QColorDialog
  • 删除二次确认：用 qfluentwidgets.MessageBox（视觉一致），按钮文案带索引和名字
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    LineEdit,
    MessageBox,
    PushButton,
    StrongBodyLabel,
)

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 样式相关常量（颜色快选 / marker / plot_type）已迁到
# preset_accordion_panel.py，编辑器只负责"基础 + 数据点"两段。

# 新曲线 / 新点的初始值
_EMPTY_CURVE: dict[str, Any] = {
    "name": "曲线",
    "color": "#1F4FE0",
    "marker": "s",
    "linewidth": 2.0,
    "markersize": 7.0,
    "plot_type": "line",
    "y_axis": "primary",
    "points": [],
}
_EMPTY_POINT: dict[str, Any] = {
    "fixed_axis": "y",
    "fixed_value": 0.0,
    "var_column": "",
    "err_column": "",
}

# 点表列顺序与标题
_POINT_COL_AXIS = 0
_POINT_COL_VALUE = 1
_POINT_COL_VAR = 2
_POINT_COL_ERR = 3
_POINT_HEADERS = ("固定轴", "固定值", "另一轴 ← 列名", "误差列（可空）")

# Y 轴选择文本（UI 显示 ↔ schema 值）
_Y_AXIS_LABELS: dict[str, str] = {"primary": "主 Y 轴", "secondary": "次 Y 轴"}
_Y_AXIS_VALUES: dict[str, str] = {v: k for k, v in _Y_AXIS_LABELS.items()}


class CurvesEditor(QWidget):
    """曲线列表 + 选中曲线字段 + 点序列子表 的组合编辑器。"""

    # 任意字段编辑后发一次。view 层做防抖再驱动 LivePreviewPane 重绘。
    changed = Signal()
    # 切曲线 / 列表变动后，当前选中曲线索引变了 → 外部「样式」分组用来重载
    current_curve_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("curvesEditor")

        # 内部状态（深拷贝独立持有）
        self._curves: list[dict[str, Any]] = []
        self._excel_headers: list[str] = []
        # 当前选中曲线索引（-1 表示未选）
        self._current_idx: int = -1
        # 信号抑制开关：在 _render_form 等"程序性"刷新时，避免 cellWidget setValue
        # 触发 changed 形成噪音
        self._suppress_signals: bool = False

        self._build_layout()
        self._refresh_curve_combo()
        self._render_form()

    # ── UI 骨架 ──────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ── 头部说明 ──
        # 用一行小字明确"曲线 ⊂ 预设"的父子关系，让用户明白：
        # 预设按钮（+新建/复制/删除）操作的是整套配置；
        # 下面的曲线按钮操作的是当前预设里的一条折线。
        hint = BodyLabel(
            "下方为「当前预设里的曲线」—— 新增/删除等操作只影响当前预设。",
            self,
        )
        hint.setStyleSheet("color: #888;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # ── 顶行：标签 + ComboBox + 5 个工具按钮（单行节省高度） ──
        top = QHBoxLayout()
        top.setSpacing(6)

        # 显式标签，与"预设选择"分组的 ComboBox 标签呼应、视觉上区分操作对象
        top.addWidget(BodyLabel("曲线", self))

        self._curve_combo = ComboBox(self)
        self._curve_combo.setObjectName("curveCombo")
        self._curve_combo.setPlaceholderText("先在右边按 + 添加曲线")
        self._curve_combo.setToolTip("曲线 = 这张图里要画的一条折线；预设可以包含 0~N 条曲线")
        self._curve_combo.currentIndexChanged.connect(self._on_curve_selected)
        top.addWidget(self._curve_combo, 1)

        # 工具按钮：QPushButton + setFixedWidth 紧凑模式，符号始终可见
        # （之前用 ToolButton 默认 IconOnly 看不到 text，已修）
        button_specs = [
            ("+", self._on_add_curve, "新增一条曲线（仅影响当前预设）"),
            ("⧉", self._on_duplicate_curve, "复制选中曲线"),
            ("×", self._on_delete_curve, "删除选中曲线"),
            ("↑", self._on_move_up, "上移选中曲线"),
            ("↓", self._on_move_down, "下移选中曲线"),
        ]
        attr_map = {
            "+": "_btn_add",
            "⧉": "_btn_dup",
            "×": "_btn_del",
            "↑": "_btn_up",
            "↓": "_btn_down",
        }
        for symbol, slot, tip in button_specs:
            btn = QPushButton(symbol, self)
            btn.setToolTip(tip)
            btn.setFixedWidth(32)
            btn.clicked.connect(slot)
            top.addWidget(btn)
            setattr(self, attr_map[symbol], btn)

        outer.addLayout(top)

        # ── 下半：选中曲线的字段编辑表单 ──
        self._form_widget = QWidget(self)
        self._form_widget.setObjectName("curveFormArea")
        self._form_layout = QVBoxLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(6)
        outer.addWidget(self._form_widget, 1)

        # ── 字段控件（按"基础 / 数据点"两组）──
        # 曲线的样式字段（图类型/颜色/点形状/线宽/点大小）已迁到外部
        # 「样式」分组的"当前曲线"子段。切曲线时外部样式区自动跟随。

        self._form_layout.addWidget(StrongBodyLabel("基础", self))
        name_row = self._make_row("曲线名:")
        self._name_edit = LineEdit(self)
        self._name_edit.editingFinished.connect(self._save_from_form)
        name_row.addWidget(self._name_edit, 1)
        self._form_layout.addLayout(name_row)

        # P1.5-④ 曲线挂哪条 Y 轴（主/次）
        # 启用次轴需要 PresetAccordionPanel 同步配次 Y 轴 spec，否则渲染时会
        # 被当作主轴；UI 显示用中文，存值用 schema 字符串 "primary"/"secondary"
        y_axis_row = self._make_row("Y 轴:")
        self._y_axis_combo = ComboBox(self)
        self._y_axis_combo.addItems(list(_Y_AXIS_LABELS.values()))
        self._y_axis_combo.setCurrentText(_Y_AXIS_LABELS["primary"])
        self._y_axis_combo.currentTextChanged.connect(self._save_from_form)
        y_axis_row.addWidget(self._y_axis_combo, 1)
        self._form_layout.addLayout(y_axis_row)

        # 点子表
        self._form_layout.addWidget(StrongBodyLabel("数据点：", self))
        self._points_table = QTableWidget(0, 4, self)
        self._points_table.setHorizontalHeaderLabels(list(_POINT_HEADERS))
        self._points_table.verticalHeader().setVisible(False)
        self._points_table.horizontalHeader().setStretchLastSection(True)
        self._points_table.horizontalHeader().setSectionResizeMode(
            _POINT_COL_AXIS, QHeaderView.ResizeMode.ResizeToContents
        )
        self._points_table.horizontalHeader().setSectionResizeMode(
            _POINT_COL_VALUE, QHeaderView.ResizeMode.ResizeToContents
        )
        self._points_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 保证至少能完整看到 4~5 行点；不被外层 QScrollArea 压扁到单行
        self._points_table.setMinimumHeight(200)
        # 去掉表格自身的 frame 边框（保留 grid 线即可）
        self._points_table.setFrameShape(QTableWidget.Shape.NoFrame)
        self._points_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._form_layout.addWidget(self._points_table, 1)

        pt_btn_row = QHBoxLayout()
        self._btn_add_pt = PushButton("+ 添加点", self)
        self._btn_add_pt.clicked.connect(self._on_add_point)
        pt_btn_row.addWidget(self._btn_add_pt)
        self._btn_del_pt = PushButton("× 删除选中点", self)
        self._btn_del_pt.clicked.connect(self._on_delete_point)
        pt_btn_row.addWidget(self._btn_del_pt)
        pt_btn_row.addStretch(1)
        self._form_layout.addLayout(pt_btn_row)

    def _make_row(self, label_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lab = BodyLabel(label_text, self)
        lab.setMinimumWidth(110)
        row.addWidget(lab)
        return row

    # ── 对外接口 ─────────────────────────────────────────────────
    def set_curves(self, curves: list[dict[str, Any]] | None) -> None:
        """喂初始 curves 列表。深拷贝持有，外部 mutate 不影响编辑器。"""
        self._curves = deepcopy(curves) if curves else []
        # 选中索引复位：列表非空时默认选第 0 条
        self._current_idx = 0 if self._curves else -1
        self._refresh_curve_combo()
        self._render_form()
        # 通知外部"样式/当前曲线"子段重载（即使 idx 没变也要刷新数据）
        self.current_curve_changed.emit(self._current_idx)

    def curves(self) -> list[dict[str, Any]]:
        """取当前编辑结果（深拷贝，外部 mutate 不污染编辑器）。"""
        return deepcopy(self._curves)

    def set_excel_headers(self, headers: list[str] | None) -> None:
        """挂载 Excel 表头：var_column 由 LineEdit 退化升级为 ComboBox。

        重新挂载会重建点表的 cellWidget。
        """
        self._excel_headers = list(headers) if headers else []
        self._render_form()

    # ── 曲线选择区 ───────────────────────────────────────────────
    @staticmethod
    def _color_icon(hex_color: str, size: int = 12) -> QIcon:
        """生成一个 size×size 的色块 QIcon。用作 ComboBox item 装饰，
        让曲线颜色用色块表达，文字本身保持主题色（适配黑/白主题）。
        """
        pix = QPixmap(size, size)
        try:
            pix.fill(QColor(hex_color))
        except Exception:
            pix.fill(QColor("#000000"))
        return QIcon(pix)

    def _refresh_curve_combo(self) -> None:
        """根据 self._curves 重建 ComboBox 内容；保持当前选中索引。"""
        self._suppress_signals = True
        try:
            self._curve_combo.clear()
            for i, c in enumerate(self._curves):
                name = str(c.get("name", "") or f"曲线 #{i + 1}")
                color = str(c.get("color", "#000000"))
                # qfluentwidgets.ComboBox.addItem 签名是 (text, icon=...)，
                # 与原生 QComboBox.addItem(icon, text) 顺序不同
                self._curve_combo.addItem(f"#{i + 1}  {name}", icon=self._color_icon(color))
            if 0 <= self._current_idx < len(self._curves):
                self._curve_combo.setCurrentIndex(self._current_idx)
            else:
                self._curve_combo.setCurrentIndex(-1)
        finally:
            self._suppress_signals = False

    def _on_curve_selected(self, idx: int) -> None:
        if self._suppress_signals or idx < 0:
            return
        self._current_idx = idx
        self._render_form()
        self.current_curve_changed.emit(idx)

    def _on_add_curve(self) -> None:
        self._curves.append(deepcopy(_EMPTY_CURVE))
        self._current_idx = len(self._curves) - 1
        self._refresh_curve_combo()
        self._render_form()
        self.current_curve_changed.emit(self._current_idx)
        self.changed.emit()

    def _on_duplicate_curve(self) -> None:
        if self._current_idx < 0:
            return
        src = self._curves[self._current_idx]
        new = deepcopy(src)
        new["name"] = f"{new.get('name', '曲线')} (副本)"
        self._curves.insert(self._current_idx + 1, new)
        self._current_idx += 1
        self._refresh_curve_combo()
        self._render_form()
        self.current_curve_changed.emit(self._current_idx)
        self.changed.emit()

    def _on_delete_curve(self) -> None:
        if self._current_idx < 0:
            return
        idx = self._current_idx
        name = str(self._curves[idx].get("name", f"#{idx + 1}"))
        # 二次确认（不可逆）
        box = MessageBox(
            "删除曲线",
            f"确认删除曲线 #{idx + 1}「{name}」？\n该操作不可撤销。",
            self.window(),
        )
        if not box.exec():
            return
        del self._curves[idx]
        if not self._curves:
            self._current_idx = -1
        elif idx >= len(self._curves):
            self._current_idx = len(self._curves) - 1
        self._refresh_curve_combo()
        self._render_form()
        self.current_curve_changed.emit(self._current_idx)
        self.changed.emit()

    def _on_move_up(self) -> None:
        if self._current_idx <= 0:
            return
        i = self._current_idx
        self._curves[i - 1], self._curves[i] = self._curves[i], self._curves[i - 1]
        self._current_idx = i - 1
        self._refresh_curve_combo()
        self.current_curve_changed.emit(self._current_idx)
        self.changed.emit()

    def _on_move_down(self) -> None:
        if self._current_idx < 0 or self._current_idx >= len(self._curves) - 1:
            return
        i = self._current_idx
        self._curves[i + 1], self._curves[i] = self._curves[i], self._curves[i + 1]
        self._current_idx = i + 1
        self._refresh_curve_combo()
        self.current_curve_changed.emit(self._current_idx)
        self.changed.emit()

    # ── 曲线字段表单 ─────────────────────────────────────────────
    def _render_form(self) -> None:
        """把当前选中曲线的字段值刷到表单控件 + 重建点表。

        样式字段（color/marker/plot_type/linewidth/markersize）已迁到
        外部「样式」分组，本编辑器只负责"基础"（曲线名 + Y 轴）和"数据点"两段。
        """
        has_selection = 0 <= self._current_idx < len(self._curves)
        self._form_widget.setEnabled(has_selection)

        self._suppress_signals = True
        try:
            if not has_selection:
                self._name_edit.setText("")
                self._y_axis_combo.setCurrentText(_Y_AXIS_LABELS["primary"])
                self._points_table.setRowCount(0)
                return

            curve = self._curves[self._current_idx]
            self._name_edit.setText(str(curve.get("name", "")))
            # Y 轴：缺省 primary；非法值退化到 primary
            y_axis_value = str(curve.get("y_axis", "primary"))
            label = _Y_AXIS_LABELS.get(y_axis_value, _Y_AXIS_LABELS["primary"])
            self._y_axis_combo.setCurrentText(label)
            self._rebuild_points_table(curve.get("points", []) or [])
        finally:
            self._suppress_signals = False

    def _save_from_form(self) -> None:
        """曲线名 / Y 轴 变化 → 回写当前曲线 + 同步 ComboBox 当前项显示文字。"""
        if self._suppress_signals or self._current_idx < 0:
            return
        curve = self._curves[self._current_idx]
        curve["name"] = self._name_edit.text()
        # Y 轴：UI 中文 → schema 字符串
        cur_label = self._y_axis_combo.currentText()
        curve["y_axis"] = _Y_AXIS_VALUES.get(cur_label, "primary")
        self._curve_combo.setItemText(
            self._current_idx, f"#{self._current_idx + 1}  {curve['name']}"
        )
        self.changed.emit()

    # ── 外部 API：供 PresetAccordionPanel 的"样式/当前曲线"子段调用 ──
    def current_curve_data(self) -> dict[str, Any] | None:
        """返回当前选中曲线的 dict（同一引用，外部 mutate 会影响内部状态）。

        样式分组通过本方法拿到曲线初值；改字段后调 update_current_curve_field。
        """
        if 0 <= self._current_idx < len(self._curves):
            return self._curves[self._current_idx]
        return None

    def update_current_curve_field(self, key: str, value: Any) -> None:
        """外部样式分组改字段时调用：写回当前曲线 + 同步显示 + emit changed。"""
        if not (0 <= self._current_idx < len(self._curves)):
            return
        self._curves[self._current_idx][key] = value
        # 颜色变化时 ComboBox 当前项色块图标跟着换
        if key == "color":
            self._curve_combo.setItemIcon(self._current_idx, self._color_icon(str(value)))
        self.changed.emit()

    # ── 点子表 ─────────────────────────────────────────────────
    def _rebuild_points_table(self, points: list[dict[str, Any]]) -> None:
        """按当前 points 列表重建表格（每行 3 个 cellWidget）。"""
        self._suppress_signals = True
        try:
            self._points_table.setRowCount(0)
            for pidx, pt in enumerate(points):
                self._points_table.insertRow(pidx)
                # axis 列：x/y ComboBox
                axis_cb = ComboBox(self._points_table)
                axis_cb.addItems(["x", "y"])
                axis_cb.setCurrentText(str(pt.get("fixed_axis", "y")))
                axis_cb.currentTextChanged.connect(
                    lambda v, r=pidx: self._on_point_axis_changed(r, v)
                )
                self._points_table.setCellWidget(pidx, _POINT_COL_AXIS, axis_cb)

                # value 列：DoubleSpinBox（范围拉大些以容纳荷载等数值）
                value_sb = DoubleSpinBox(self._points_table)
                value_sb.setRange(-1e9, 1e9)
                value_sb.setDecimals(3)
                try:
                    value_sb.setValue(float(pt.get("fixed_value", 0.0)))
                except (TypeError, ValueError):
                    value_sb.setValue(0.0)
                value_sb.valueChanged.connect(lambda v, r=pidx: self._on_point_value_changed(r, v))
                self._points_table.setCellWidget(pidx, _POINT_COL_VALUE, value_sb)

                # var_column 列：有 Excel 表头 → ComboBox（可编辑），否则普通 LineEdit
                var_widget: QWidget
                cur_var = str(pt.get("var_column", ""))
                if self._excel_headers:
                    cb = ComboBox(self._points_table)
                    cb.addItems(self._excel_headers)
                    if cur_var in self._excel_headers:
                        cb.setCurrentText(cur_var)
                    elif cur_var:
                        # 当前值不在表头里：用 setCurrentText 让 ComboBox 显示原值
                        # （但 ComboBox 不可编辑时 setCurrentText 会被忽略；
                        # 这里加 hint 给用户看到"未匹配"）
                        cb.insertItem(0, cur_var)
                        cb.setCurrentIndex(0)
                    cb.currentTextChanged.connect(
                        lambda v, r=pidx: self._on_point_var_changed(r, v)
                    )
                    var_widget = cb
                else:
                    le = QLineEdit(self._points_table)
                    le.setText(cur_var)
                    le.editingFinished.connect(
                        lambda r=pidx, w=le: self._on_point_var_changed(r, w.text())
                    )
                    var_widget = le
                self._points_table.setCellWidget(pidx, _POINT_COL_VAR, var_widget)

                # err_column 列（P1.5-④ 误差棒）：空字符串=不画误差
                # 风格与 var_column 列一致：有 Excel 表头 → ComboBox，否则 LineEdit
                # 第一项加"(无)"代表空字符串，避免用户必须输入空格
                err_widget: QWidget
                cur_err = str(pt.get("err_column", ""))
                if self._excel_headers:
                    cb_err = ComboBox(self._points_table)
                    cb_err.addItem("(无)")
                    cb_err.addItems(self._excel_headers)
                    if cur_err in self._excel_headers:
                        cb_err.setCurrentText(cur_err)
                    elif cur_err:
                        # 当前值不在表头：插到下拉里让用户看见，不丢
                        cb_err.insertItem(1, cur_err)
                        cb_err.setCurrentIndex(1)
                    else:
                        cb_err.setCurrentIndex(0)  # (无)
                    cb_err.currentTextChanged.connect(
                        lambda v, r=pidx: self._on_point_err_changed(r, "" if v == "(无)" else v)
                    )
                    err_widget = cb_err
                else:
                    le_err = QLineEdit(self._points_table)
                    le_err.setText(cur_err)
                    le_err.setPlaceholderText("(无)")
                    le_err.editingFinished.connect(
                        lambda r=pidx, w=le_err: self._on_point_err_changed(r, w.text())
                    )
                    err_widget = le_err
                self._points_table.setCellWidget(pidx, _POINT_COL_ERR, err_widget)
        finally:
            self._suppress_signals = False

    def _current_points(self) -> list[dict[str, Any]] | None:
        if self._current_idx < 0:
            return None
        return self._curves[self._current_idx].setdefault("points", [])

    def _on_point_axis_changed(self, row: int, value: str) -> None:
        if self._suppress_signals:
            return
        pts = self._current_points()
        if pts is None or row >= len(pts):
            return
        pts[row]["fixed_axis"] = value
        self.changed.emit()

    def _on_point_value_changed(self, row: int, value: float) -> None:
        if self._suppress_signals:
            return
        pts = self._current_points()
        if pts is None or row >= len(pts):
            return
        pts[row]["fixed_value"] = float(value)
        self.changed.emit()

    def _on_point_var_changed(self, row: int, value: str) -> None:
        if self._suppress_signals:
            return
        pts = self._current_points()
        if pts is None or row >= len(pts):
            return
        pts[row]["var_column"] = value
        self.changed.emit()

    def _on_point_err_changed(self, row: int, value: str) -> None:
        """P1.5-④：误差列字段变化。空字符串视为"不画误差棒"。"""
        if self._suppress_signals:
            return
        pts = self._current_points()
        if pts is None or row >= len(pts):
            return
        pts[row]["err_column"] = value
        self.changed.emit()

    def _on_add_point(self) -> None:
        pts = self._current_points()
        if pts is None:
            return
        pts.append(deepcopy(_EMPTY_POINT))
        self._rebuild_points_table(pts)
        self.changed.emit()

    def _on_delete_point(self) -> None:
        pts = self._current_points()
        if pts is None:
            return
        # 取当前选中行；若没选则删最后一行
        row = self._points_table.currentRow()
        if row < 0 or row >= len(pts):
            if not pts:
                return
            row = len(pts) - 1
        del pts[row]
        self._rebuild_points_table(pts)
        self.changed.emit()
