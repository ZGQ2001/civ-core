"""数据源 Tab（L-4 实装）—— 用表格显示当前 Excel 数据源的"关键映射列"。

为什么需要这个面板
==================
  • 出图前用户经常想看 "这张 Excel 里 var_column 实际值是啥" 来判断预设对不对
  • 把整张 Excel 全部显示信息密度太低（仪器导出几十列噪音）；过滤到
    预设真正用到的列，既能验证列名匹配，又不被无关列干扰

显示策略
========
  • set_preset_and_data(preset, rows) 时把要显示的列收齐：
      keys = [preset["id_column"]] + 所有 curves[*].points[*].var_column 去重
  • 若 keys 为空（新预设 / curves 未填）→ 兜底显示前 3 列
  • QTableView + QStandardItemModel，整行选中模式
  • 行点击 → emit row_highlighted(int)：让 LivePreviewPane 在图上突出该行
  • highlight_row(int)：外部反向调用，让表格滚动到指定行并高亮
    （目前只有"表格 → 预览"自动联动；"预览 → 表格"留 P1.5）

CLAUDE.md 合规
==============
  • 业务/IO/UI 分离：本类不直接读 Excel，rows 由调用方（view）从
    ExcelDataCache 拿到再喂进来
  • 设计上不持有 path —— path 是 view 的事，本类只负责展示
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel

from civ_core.utils.logger import get_logger

log = get_logger(__name__)

# 兜底：preset 没给 keys 时显示的最大列数
_FALLBACK_COL_LIMIT = 3


class DataSourcePane(QWidget):
    """显示当前 Excel 数据的"关键列"。"""

    # 用户在表格里点行 → 通知外部（view 转 LivePreviewPane.highlight_row）
    row_highlighted = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dataSourcePane")
        # 显式允许窄宽：avoid 被表格内容（11+ 列长表头）撑出最小宽度，
        # 进而把 BottomTabPanel / 右栏 / 主窗口都拉过宽度（截图反馈的 bug）
        self.setMinimumWidth(0)

        self._all_rows: list[dict[str, Any]] = []
        self._displayed_cols: list[str] = []
        # 标记位：highlight_row 是外部反向调用，不应触发 row_highlighted 形成回路
        self._suppress_emit: bool = False

        self._build_layout()
        self._update_status_text()

    # ── UI 骨架 ──────────────────────────────────────────────────
    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self._status = BodyLabel("尚未挂载数据源", self)
        self._status.setStyleSheet("color: #666;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._table = QTableView(self)
        self._table.setObjectName("dataSourceTable")
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        # 关键修复：列宽用 Interactive + 固定默认值，不再 ResizeToContents
        # ResizeToContents 会让"15.0kN (0.1Nd) 位移读数"这种长表头把列撑到
        # ~150px，11 列总宽 ~1500px → 整个 widget sizeHint 撑大 → 主窗口被
        # 拉过屏幕。Interactive 让用户拖宽度，超出可视区由横向滚动条接管。
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(140)
        header.setMinimumSectionSize(60)

        # 横向 / 竖向滚动条按需出现（横向是本次修复的关键：列宽超出时能滚）
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # 横向滚一格 = 一个像素，比"一格 = 一列"在长表头时手感更好
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # 让表格本身的 sizePolicy 不强求空间：Ignored 让外层 layout 自由分配
        self._table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self._model = QStandardItemModel(0, 0, self)
        self._table.setModel(self._model)
        sel = self._table.selectionModel()
        if sel is not None:
            sel.currentRowChanged.connect(self._on_current_row_changed)

        layout.addWidget(self._table, 1)

    # ── 对外接口 ─────────────────────────────────────────────────
    def set_preset_and_data(
        self,
        preset: dict[str, Any] | None,
        rows: list[dict[str, Any]] | None,
    ) -> None:
        """喂当前预设字段 + Excel 行数据。会按预设收齐"关键列"重建模型。

        preset / rows 任一为 None 视作"清空"。
        """
        if not preset or not rows:
            self._all_rows = []
            self._displayed_cols = []
            self._rebuild_model()
            return

        # 收集要显示的列：id_column + 所有 curves[*].points[*].var_column 去重
        keys: list[str] = []
        id_col = preset.get("id_column")
        if id_col:
            keys.append(str(id_col))
        for curve in preset.get("curves") or []:
            if not isinstance(curve, dict):
                continue
            for pt in curve.get("points") or []:
                if not isinstance(pt, dict):
                    continue
                v = pt.get("var_column")
                if v and v not in keys:
                    keys.append(str(v))

        # 兜底：keys 为空（新预设 / curves 未填） → 显示前 N 列
        if not keys and rows:
            keys = list(rows[0].keys())[:_FALLBACK_COL_LIMIT]

        self._displayed_cols = keys
        self._all_rows = rows
        self._rebuild_model()

    def highlight_row(self, idx: int) -> None:
        """外部反向调用：滚到 idx 行并选中。不触发 row_highlighted 形成回路。"""
        if not (0 <= idx < self._model.rowCount()):
            return
        self._suppress_emit = True
        try:
            self._table.selectRow(idx)
            self._table.scrollTo(
                self._model.index(idx, 0),
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )
        finally:
            self._suppress_emit = False

    def clear(self) -> None:
        """清空显示（数据源被撤销时）。"""
        self._all_rows = []
        self._displayed_cols = []
        self._rebuild_model()

    # ── 内部 ──────────────────────────────────────────────────────
    def _rebuild_model(self) -> None:
        """根据 _all_rows / _displayed_cols 重建 QStandardItemModel。"""
        self._model.clear()
        if not self._displayed_cols:
            self._update_status_text()
            return

        self._model.setHorizontalHeaderLabels(self._displayed_cols)
        for r in self._all_rows:
            items: list[QStandardItem] = []
            for col in self._displayed_cols:
                v = r.get(col)
                # None / NaN 显示为空字符串；其它转 str
                if v is None or (isinstance(v, float) and v != v):
                    text = ""
                else:
                    text = str(v)
                item = QStandardItem(text)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                items.append(item)
            self._model.appendRow(items)

        # 列宽固定走 _build_layout 里的 Interactive + defaultSectionSize=140
        # 不再 ResizeToContents（会让长表头列被撑过宽，触发右栏整体扩张）
        # 用户可以手动拖列宽，超出可视区由横向滚动条接管
        self._update_status_text()

    def _update_status_text(self) -> None:
        if not self._displayed_cols:
            self._status.setText("尚未挂载数据源")
        else:
            cols_text = " / ".join(self._displayed_cols)
            self._status.setText(
                f"{len(self._all_rows)} 行 × {len(self._displayed_cols)} 列（显示列：{cols_text}）"
            )

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if self._suppress_emit:
            return
        if not current.isValid():
            return
        self.row_highlighted.emit(current.row())
