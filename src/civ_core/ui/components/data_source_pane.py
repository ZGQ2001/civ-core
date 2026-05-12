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
        layout.addWidget(self._status)

        self._table = QTableView(self)
        self._table.setObjectName("dataSourceTable")
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        # 大数据时关掉 alternatingRowColors 会更省渲染开销
        self._table.setAlternatingRowColors(True)
        # 列宽：第一列略宽，其余 ResizeToContents
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultSectionSize(120)

        self._model = QStandardItemModel(0, 0, self)
        self._table.setModel(self._model)
        # 选择变化（包含 click + 键盘）触发 highlighted；selectRow 触发
        # selectionChanged 也会进来 —— 用 _suppress_emit 守门避免回路
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
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                items.append(item)
            self._model.appendRow(items)

        # 列宽自适应；最后一列保持 stretch（_build_layout 里设置过）
        for i in range(len(self._displayed_cols) - 1):
            self._table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents
            )

        self._update_status_text()

    def _update_status_text(self) -> None:
        if not self._displayed_cols:
            self._status.setText("尚未挂载数据源")
        else:
            cols_text = " / ".join(self._displayed_cols)
            self._status.setText(
                f"{len(self._all_rows)} 行 × {len(self._displayed_cols)} 列"
                f"（显示列：{cols_text}）"
            )

    def _on_current_row_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        if self._suppress_emit:
            return
        if not current.isValid():
            return
        self.row_highlighted.emit(current.row())
