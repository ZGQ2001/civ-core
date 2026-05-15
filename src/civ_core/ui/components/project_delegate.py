"""ProjectDelegate：QStyledItemDelegate 自定义渲染，Linear 极简风格，行高 40px。

每行绘制：
  左侧 4px 色条 + 状态圆点（○/●/✅）+ 编号 · 名称 · 类型 · 金额 · 微型进度条
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from civ_core.ui.models.project_list_model import ProjectListModel

# ── 颜色常量 ─────────────────────────────────────────────────────
_COLOR_DOT_PENDING = QColor("#9E9E9E")     # ○ 灰色
_COLOR_DOT_ACTIVE = QColor("#1976D2")       # ● 蓝色
_COLOR_DOT_DONE = QColor("#4CAF50")          # ✅ 绿色
_COLOR_TEXT_PRIMARY = QColor("#212121")
_COLOR_TEXT_SECONDARY = QColor("#757575")
_COLOR_AMOUNT = QColor("#1565C0")
_COLOR_STRIP = QColor("#E0E0E0")            # 进度条背景
_COLOR_STRIP_FILL = QColor("#1976D2")       # 进度条填充
_COLOR_BAR = QColor("#1976D2")              # 左侧色条


class ProjectDelegate(QStyledItemDelegate):
    """项目列表行委托：40px 行高，Linear 极简风格。"""

    _ROW_HEIGHT = 44

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
        bar_rect = QRect(
            option.rect.left(), option.rect.top(), 4, option.rect.height()
        )
        painter.fillRect(bar_rect, _COLOR_BAR)

        x = option.rect.left() + 14  # 色条右边留白 10px

        # ── 状态圆点 ────────────────────────────────────────────
        stage_text = index.data(ProjectListModel.ProgressRole) or "0/7"
        completed = int(stage_text.split("/")[0]) if "/" in stage_text else 0

        if completed == 7:
            dot_color = _COLOR_DOT_DONE
        elif completed > 0:
            dot_color = _COLOR_DOT_ACTIVE
        else:
            dot_color = _COLOR_DOT_PENDING

        dot_radius = 4
        dot_cx = x + dot_radius
        dot_cy = option.rect.top() + option.rect.height() // 2
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(dot_cx - dot_radius), int(dot_cy - dot_radius),
            dot_radius * 2, dot_radius * 2,
        )
        x += dot_radius * 2 + 8

        # ── 编号 ────────────────────────────────────────────────
        number = index.data(ProjectListModel.ProjectNumberRole) or ""
        font_small = QFont(painter.font())
        font_small.setPixelSize(12)
        painter.setFont(font_small)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        num_rect = QRect(x, option.rect.top(), 60, option.rect.height())
        painter.drawText(num_rect, Qt.AlignmentFlag.AlignVCenter, number)
        x += 64

        # ── 名称 ────────────────────────────────────────────────
        name = index.data(ProjectListModel.NameRole) or ""
        font_name = QFont(painter.font())
        font_name.setPixelSize(13)
        font_name.setBold(True)
        painter.setFont(font_name)
        painter.setPen(_COLOR_TEXT_PRIMARY)
        name_rect = QRect(x, option.rect.top(), 200, option.rect.height())
        elided = painter.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideRight, 200
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        x += 208

        # ── 类型 ────────────────────────────────────────────────
        itype = index.data(ProjectListModel.InspectionTypeRole) or ""
        painter.setFont(font_small)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        itype_rect = QRect(x, option.rect.top(), 90, option.rect.height())
        elided_type = painter.fontMetrics().elidedText(
            itype, Qt.TextElideMode.ElideRight, 90
        )
        painter.drawText(itype_rect, Qt.AlignmentFlag.AlignVCenter, elided_type)
        x += 98

        # ── 金额 ────────────────────────────────────────────────
        amount = index.data(ProjectListModel.AmountRole) or 0.0
        amount_str = f"¥{amount:,.0f}" if amount >= 1000 else f"¥{amount:.0f}"
        painter.setPen(_COLOR_AMOUNT)
        amt_rect = QRect(x, option.rect.top(), 80, option.rect.height())
        painter.drawText(amt_rect, Qt.AlignmentFlag.AlignVCenter, amount_str)
        x += 88

        # ── 微型进度条 ──────────────────────────────────────────
        bar_width = 60
        bar_height = 6
        bar_y = option.rect.top() + (option.rect.height() - bar_height) // 2
        bar_rect = QRect(x, bar_y, bar_width, bar_height)

        # 背景
        painter.setBrush(QBrush(_COLOR_STRIP))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_rect, 3, 3)

        # 填充
        if completed > 0:
            fill_width = int(bar_width * completed / 7)
            fill_rect = QRect(x, bar_y, fill_width, bar_height)
            painter.setBrush(QBrush(_COLOR_STRIP_FILL))
            painter.drawRoundedRect(fill_rect, 3, 3)

        # 进度文字
        x += bar_width + 6
        progress_text = stage_text
        painter.setFont(font_small)
        painter.setPen(_COLOR_TEXT_SECONDARY)
        prog_rect = QRect(x, option.rect.top(), 30, option.rect.height())
        painter.drawText(prog_rect, Qt.AlignmentFlag.AlignVCenter, progress_text)

        painter.restore()
