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
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
    ToolButton,
)

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 6 个常用色：来自旧版 COMMON_COLORS，保留兼容
_QUICK_COLORS: tuple[str, ...] = (
    "#1F4FE0",  # 蓝
    "#E03A3A",  # 红
    "#1AAA55",  # 绿
    "#FFA500",  # 橙
    "#9C27B0",  # 紫
    "#000000",  # 黑
)

# matplotlib 兼容的 marker 集合（与旧版一致 + 顺序）
_MARKER_CHOICES: tuple[str, ...] = ("s", "o", "^", "v", "D", "x", "*", "+")

# 新曲线 / 新点的初始值
_EMPTY_CURVE: dict[str, Any] = {
    "name": "曲线",
    "color": "#1F4FE0",
    "marker": "s",
    "linewidth": 2.0,
    "markersize": 7.0,
    "points": [],
}
_EMPTY_POINT: dict[str, Any] = {
    "fixed_axis": "y",
    "fixed_value": 0.0,
    "var_column": "",
}

# 点表列顺序与标题
_POINT_COL_AXIS = 0
_POINT_COL_VALUE = 1
_POINT_COL_VAR = 2
_POINT_HEADERS = ("固定轴", "固定值", "另一轴 ← 列名")


class CurvesEditor(QWidget):
    """曲线列表 + 选中曲线字段 + 点序列子表 的组合编辑器。"""

    # 任意字段编辑后发一次。view 层做防抖再驱动 LivePreviewPane 重绘。
    changed = Signal()

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
        self._refresh_curve_list()
        self._render_form()

    # ── UI 骨架 ──────────────────────────────────────────────────
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ── 上半：曲线列表 + 工具栏 ──
        top = QHBoxLayout()
        top.setSpacing(8)

        # 左：曲线列表
        self._curve_list = QListWidget(self)
        self._curve_list.setObjectName("curveList")
        self._curve_list.setMaximumHeight(140)
        self._curve_list.currentRowChanged.connect(self._on_curve_selected)
        top.addWidget(self._curve_list, 1)

        # 右：增/复制/删除/↑/↓ 工具栏
        toolbar = QVBoxLayout()
        toolbar.setSpacing(4)
        self._btn_add = ToolButton("+", self)
        self._btn_add.setToolTip("新增曲线")
        self._btn_add.clicked.connect(self._on_add_curve)
        toolbar.addWidget(self._btn_add)

        self._btn_dup = ToolButton("⧉", self)
        self._btn_dup.setToolTip("复制选中曲线")
        self._btn_dup.clicked.connect(self._on_duplicate_curve)
        toolbar.addWidget(self._btn_dup)

        self._btn_del = ToolButton("×", self)
        self._btn_del.setToolTip("删除选中曲线")
        self._btn_del.clicked.connect(self._on_delete_curve)
        toolbar.addWidget(self._btn_del)

        self._btn_up = ToolButton("↑", self)
        self._btn_up.setToolTip("上移选中曲线")
        self._btn_up.clicked.connect(self._on_move_up)
        toolbar.addWidget(self._btn_up)

        self._btn_down = ToolButton("↓", self)
        self._btn_down.setToolTip("下移选中曲线")
        self._btn_down.clicked.connect(self._on_move_down)
        toolbar.addWidget(self._btn_down)

        toolbar.addStretch(1)
        top.addLayout(toolbar)
        outer.addLayout(top)

        # ── 下半：选中曲线的字段编辑表单 ──
        self._form_widget = QWidget(self)
        self._form_widget.setObjectName("curveFormArea")
        self._form_layout = QVBoxLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(6)
        outer.addWidget(self._form_widget, 1)

        # ── 字段控件（统一构造一次，刷新时只 setValue / 不重建）──
        # 名称
        name_row = self._make_row("曲线名:")
        self._name_edit = LineEdit(self)
        self._name_edit.editingFinished.connect(self._save_from_form)
        name_row.addWidget(self._name_edit, 1)
        self._form_layout.addLayout(name_row)

        # 颜色（快选按钮 + 调色板按钮 + 当前色显示）
        color_row = self._make_row("颜色:")
        self._color_swatches: list[QPushButton] = []
        for hex_color in _QUICK_COLORS:
            btn = QPushButton(self)
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                f"QPushButton {{ background: {hex_color}; border: 1px solid #888; border-radius: 3px; }}"
                f"QPushButton:hover {{ border: 2px solid #333; }}"
            )
            btn.setToolTip(hex_color)
            btn.clicked.connect(lambda _=False, c=hex_color: self._set_color(c))
            color_row.addWidget(btn)
            self._color_swatches.append(btn)
        self._btn_color_dialog = PushButton("更多…", self)
        self._btn_color_dialog.clicked.connect(self._open_color_dialog)
        color_row.addWidget(self._btn_color_dialog)
        # 当前色显示：右侧小色块 + hex 文字
        self._color_indicator = QPushButton(self)
        self._color_indicator.setFixedSize(40, 22)
        self._color_indicator.setEnabled(False)  # 仅显示
        color_row.addWidget(self._color_indicator)
        color_row.addStretch(1)
        self._form_layout.addLayout(color_row)

        # marker
        marker_row = self._make_row("标记:")
        self._marker_combo = ComboBox(self)
        self._marker_combo.addItems(list(_MARKER_CHOICES))
        self._marker_combo.currentTextChanged.connect(self._save_from_form)
        marker_row.addWidget(self._marker_combo)
        marker_row.addStretch(1)
        self._form_layout.addLayout(marker_row)

        # linewidth + markersize（一行两个）
        sizes_row = self._make_row("线宽 / 标记尺寸:")
        self._linewidth_spin = DoubleSpinBox(self)
        self._linewidth_spin.setRange(0.1, 10.0)
        self._linewidth_spin.setSingleStep(0.5)
        self._linewidth_spin.setDecimals(1)
        self._linewidth_spin.valueChanged.connect(self._save_from_form)
        sizes_row.addWidget(self._linewidth_spin)
        self._markersize_spin = DoubleSpinBox(self)
        self._markersize_spin.setRange(0.0, 20.0)
        self._markersize_spin.setSingleStep(0.5)
        self._markersize_spin.setDecimals(1)
        self._markersize_spin.valueChanged.connect(self._save_from_form)
        sizes_row.addWidget(self._markersize_spin)
        sizes_row.addStretch(1)
        self._form_layout.addLayout(sizes_row)

        # 点子表
        self._form_layout.addWidget(StrongBodyLabel("数据点：", self))
        self._points_table = QTableWidget(0, 3, self)
        self._points_table.setHorizontalHeaderLabels(list(_POINT_HEADERS))
        self._points_table.verticalHeader().setVisible(False)
        self._points_table.horizontalHeader().setStretchLastSection(True)
        self._points_table.horizontalHeader().setSectionResizeMode(
            _POINT_COL_AXIS, QHeaderView.ResizeMode.ResizeToContents
        )
        self._points_table.horizontalHeader().setSectionResizeMode(
            _POINT_COL_VALUE, QHeaderView.ResizeMode.ResizeToContents
        )
        self._points_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._points_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
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
        self._refresh_curve_list()
        self._render_form()

    def curves(self) -> list[dict[str, Any]]:
        """取当前编辑结果（深拷贝，外部 mutate 不污染编辑器）。"""
        return deepcopy(self._curves)

    def set_excel_headers(self, headers: list[str] | None) -> None:
        """挂载 Excel 表头：var_column 由 LineEdit 退化升级为 ComboBox。

        重新挂载会重建点表的 cellWidget。
        """
        self._excel_headers = list(headers) if headers else []
        self._render_form()

    # ── 曲线列表区 ───────────────────────────────────────────────
    def _refresh_curve_list(self) -> None:
        """根据 self._curves 重建左侧 QListWidget；保持当前选中索引（如有效）。"""
        self._suppress_signals = True
        try:
            self._curve_list.clear()
            for i, c in enumerate(self._curves):
                name = str(c.get("name", "") or f"曲线 #{i + 1}")
                item = QListWidgetItem(f"#{i + 1}  {name}")
                # 把曲线颜色作为 item 前缀色（简单实现：item 文字色）
                color = str(c.get("color", "#000000"))
                item.setForeground(QColor(color))
                self._curve_list.addItem(item)
            if 0 <= self._current_idx < len(self._curves):
                self._curve_list.setCurrentRow(self._current_idx)
        finally:
            self._suppress_signals = False

    def _on_curve_selected(self, idx: int) -> None:
        if self._suppress_signals:
            return
        self._current_idx = idx
        self._render_form()

    def _on_add_curve(self) -> None:
        self._curves.append(deepcopy(_EMPTY_CURVE))
        self._current_idx = len(self._curves) - 1
        self._refresh_curve_list()
        self._render_form()
        self.changed.emit()

    def _on_duplicate_curve(self) -> None:
        if self._current_idx < 0:
            return
        src = self._curves[self._current_idx]
        new = deepcopy(src)
        new["name"] = f"{new.get('name', '曲线')} (副本)"
        self._curves.insert(self._current_idx + 1, new)
        self._current_idx += 1
        self._refresh_curve_list()
        self._render_form()
        self.changed.emit()

    def _on_delete_curve(self) -> None:
        if self._current_idx < 0:
            return
        idx = self._current_idx
        name = str(self._curves[idx].get("name", f"#{idx + 1}"))
        # 二次确认：删除是不可逆操作，用 MessageBox 拦一道
        box = MessageBox(
            "删除曲线",
            f"确认删除曲线 #{idx + 1}「{name}」？\n该操作不可撤销。",
            self.window(),
        )
        if not box.exec():
            return
        del self._curves[idx]
        # 删除后选中调整
        if not self._curves:
            self._current_idx = -1
        elif idx >= len(self._curves):
            self._current_idx = len(self._curves) - 1
        # else 保持 idx 不变（指向"原来的下一条"）
        self._refresh_curve_list()
        self._render_form()
        self.changed.emit()

    def _on_move_up(self) -> None:
        if self._current_idx <= 0:
            return
        i = self._current_idx
        self._curves[i - 1], self._curves[i] = self._curves[i], self._curves[i - 1]
        self._current_idx = i - 1
        self._refresh_curve_list()
        self.changed.emit()

    def _on_move_down(self) -> None:
        if self._current_idx < 0 or self._current_idx >= len(self._curves) - 1:
            return
        i = self._current_idx
        self._curves[i + 1], self._curves[i] = self._curves[i], self._curves[i + 1]
        self._current_idx = i + 1
        self._refresh_curve_list()
        self.changed.emit()

    # ── 曲线字段表单 ─────────────────────────────────────────────
    def _render_form(self) -> None:
        """把当前选中曲线的字段值刷到表单控件 + 重建点表。

        suppress_signals 期间设值，避免 valueChanged 触发 _save_from_form
        反向写回（会触发 changed，干扰测试）。
        """
        has_selection = 0 <= self._current_idx < len(self._curves)
        self._form_widget.setEnabled(has_selection)

        self._suppress_signals = True
        try:
            if not has_selection:
                self._name_edit.setText("")
                self._marker_combo.setCurrentIndex(0)
                self._linewidth_spin.setValue(2.0)
                self._markersize_spin.setValue(7.0)
                self._set_color_indicator("#1F4FE0")
                self._points_table.setRowCount(0)
                return

            curve = self._curves[self._current_idx]
            self._name_edit.setText(str(curve.get("name", "")))

            color = str(curve.get("color", "#1F4FE0"))
            self._set_color_indicator(color)

            marker = str(curve.get("marker", "s"))
            if marker in _MARKER_CHOICES:
                self._marker_combo.setCurrentIndex(_MARKER_CHOICES.index(marker))

            try:
                self._linewidth_spin.setValue(float(curve.get("linewidth", 2.0)))
            except (TypeError, ValueError):
                self._linewidth_spin.setValue(2.0)
            try:
                self._markersize_spin.setValue(float(curve.get("markersize", 7.0)))
            except (TypeError, ValueError):
                self._markersize_spin.setValue(7.0)

            self._rebuild_points_table(curve.get("points", []) or [])
        finally:
            self._suppress_signals = False

    def _set_color_indicator(self, hex_color: str) -> None:
        self._color_indicator.setText(hex_color.upper())
        self._color_indicator.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; color: #fff; "
            f"text-shadow: 0 0 2px #000; border: 1px solid #888; }}"
        )

    def _set_color(self, hex_color: str) -> None:
        if self._current_idx < 0:
            return
        self._curves[self._current_idx]["color"] = hex_color
        self._set_color_indicator(hex_color)
        # 列表里那条曲线的文字色也跟着更新
        item = self._curve_list.item(self._current_idx)
        if item is not None:
            item.setForeground(QColor(hex_color))
        self.changed.emit()

    def _open_color_dialog(self) -> None:
        if self._current_idx < 0:
            return
        cur = QColor(str(self._curves[self._current_idx].get("color", "#1F4FE0")))
        chosen = QColorDialog.getColor(cur, self, "选择曲线颜色")
        if chosen.isValid():
            self._set_color(chosen.name())

    def _save_from_form(self) -> None:
        """文本/数值控件 valueChanged → 回写到 self._curves[idx]。"""
        if self._suppress_signals or self._current_idx < 0:
            return
        curve = self._curves[self._current_idx]
        curve["name"] = self._name_edit.text()
        curve["marker"] = self._marker_combo.currentText()
        curve["linewidth"] = float(self._linewidth_spin.value())
        curve["markersize"] = float(self._markersize_spin.value())
        # 名称改了，列表显示也要同步
        item = self._curve_list.item(self._current_idx)
        if item is not None:
            item.setText(f"#{self._current_idx + 1}  {curve['name']}")
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
                value_sb.valueChanged.connect(
                    lambda v, r=pidx: self._on_point_value_changed(r, v)
                )
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
