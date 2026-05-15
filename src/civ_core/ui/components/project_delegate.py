"""ProjectDelegate：QStyledItemDelegate，使用 COL_WIDTHS 实现像素级对齐。

行高 48px，逐列按 COL_WIDTHS 计算 X 偏移量。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from civ_core.ui.models.project_list_model import COL_WIDTHS, ProjectListModel

_COLOR_DOT_PENDING = QColor("#9E9E9E")
_COLOR_DOT_ACTIVE = QColor("#1976D2")
_COLOR_DOT_DONE = QColor("#4CAF50")
_COLOR_TEXT_PRIMARY = QColor("#212121")
_COLOR_TEXT_SECONDARY = QColor("#757575")
_COLOR_AMOUNT = QColor("#1565C0")
_COLOR_STRIP = QColor("#E0E0E0")
_COLOR_STRIP_FILL = QColor("#1976D2")
_COLOR_BAR = QColor("#1976D2")
_COLOR_DATE = QColor("#9E9E9E")


class ProjectDelegate(QStyledItemDelegate):

    _ROW_HEIGHT = 48

    def row_height(self) -> int:
        return self._ROW_HEIGHT

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(0, self._ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#E3F2FD"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor("#F5F5F5"))
        else:
            painter.fillRect(option.rect, Qt.GlobalColor.white)

        # 左侧 4px 色条
        bar_rect = QRect(option.rect.left(), option.rect.top(), 4, option.rect.height())
        painter.fillRect(bar_rect, _COLOR_BAR)

        # 起点 X：色条右侧 + 留白
        x_base = option.rect.left() + 12
        y_mid = option.rect.top()
        row_h = option.rect.height()

        # ── 1. 状态圆点 ──────────────────────────────────────────
        stage_text = index.data(ProjectListModel.ProgressRole) or "0/7"
        completed = int(stage_text.split("/")[0]) if "/" in stage_text else 0

        if completed == 7:
            dot_color = _COLOR_DOT_DONE
        elif completed > 0:
            dot_color = _COLOR_DOT_ACTIVE
        else:
            dot_color = _COLOR_DOT_PENDING

        dot_r = 4
        dot_cx = x_base + COL_WIDTHS["status"] // 2
        dot_cy = y_mid + row_h // 2
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(dot_cx - dot_r), int(dot_cy - dot_r), dot_r * 2, dot_r * 2)

        font_primary = QFont(painter.font())
        font_primary.setPixelSize(13)
        font_secondary = QFont(painter.font())
        font_secondary.setPixelSize(12)
        x = x_base + COL_WIDTHS["status"] + COL_WIDTHS["dot_pad"]

        # ── 2. 编号 ──────────────────────────────────────────────
        number = index.data(ProjectListModel.ProjectNumberRole) or ""
        painter.setFont(font_secondary)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["number"], row_h),
                         Qt.AlignmentFlag.AlignVCenter, number)
        x += COL_WIDTHS["number"]

        # ── 3. 名称 ──────────────────────────────────────────────
        name = index.data(ProjectListModel.NameRole) or ""
        font_name = QFont(painter.font())
        font_name.setPixelSize(13)
        font_name.setBold(True)
        painter.setFont(font_name)
        painter.setPen(_COLOR_TEXT_PRIMARY)
        elided = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, COL_WIDTHS["name"])
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["name"], row_h),
                         Qt.AlignmentFlag.AlignVCenter, elided)
        x += COL_WIDTHS["name"]

        # ── 4. 类型 ──────────────────────────────────────────────
        itype = index.data(ProjectListModel.InspectionTypeRole) or ""
        painter.setFont(font_secondary)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        elided_t = painter.fontMetrics().elidedText(itype, Qt.TextElideMode.ElideRight, COL_WIDTHS["type"])
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["type"], row_h),
                         Qt.AlignmentFlag.AlignVCenter, elided_t)
        x += COL_WIDTHS["type"]

        # ── 5. 金额 ──────────────────────────────────────────────
        amount = index.data(ProjectListModel.AmountRole) or 0.0
        amount_str = f"¥{amount:,.0f}" if amount >= 1000 else f"¥{amount:.0f}"
        painter.setPen(_COLOR_AMOUNT)
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["amount"], row_h),
                         Qt.AlignmentFlag.AlignVCenter, amount_str)
        x += COL_WIDTHS["amount"]

        # ── 6. 日期 ──────────────────────────────────────────────
        date_str = index.data(ProjectListModel.DateRole) or ""
        painter.setFont(font_secondary)
        painter.setPen(_COLOR_DATE)
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["date"], row_h),
                         Qt.AlignmentFlag.AlignVCenter, date_str)
        x += COL_WIDTHS["date"]

        # ── 7. 微型进度条 ────────────────────────────────────────
        bar_w = 50
        bar_h = 6
        bar_y = y_mid + (row_h - bar_h) // 2
        bg_rect = QRect(x, bar_y, bar_w, bar_h)
        painter.setBrush(QBrush(_COLOR_STRIP))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 3, 3)

        if completed > 0:
            fill_w = int(bar_w * completed / 7)
            painter.setBrush(QBrush(_COLOR_STRIP_FILL))
            painter.drawRoundedRect(QRect(x, bar_y, fill_w, bar_h), 3, 3)

        x += bar_w + 4
        painter.setFont(font_secondary)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        painter.drawText(QRect(x, y_mid, COL_WIDTHS["progress"] - bar_w - 4, row_h),
                         Qt.AlignmentFlag.AlignVCenter, stage_text)

        painter.restore()
