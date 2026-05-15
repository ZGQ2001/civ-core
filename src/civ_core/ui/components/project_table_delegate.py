"""ProjectTableDelegate：名称列 ElideMiddle + Tooltip，其余列默认渲染。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QToolTip

from civ_core.ui.models.project_table_model import ProjectTableModel


class ProjectTableDelegate(QStyledItemDelegate):
    """表格行委托：名称列中间截断 + 悬停 Tooltip。"""

    def paint(self, painter, option, index):
        if index.column() == ProjectTableModel.NameCol:
            painter.save()
            # 选中态背景
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            # 绘制截断文本
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            elided = option.fontMetrics.elidedText(text, Qt.TextElideMode.ElideMiddle, option.rect.width() - 8)
            painter.setPen(
                option.palette.highlightedText().color()
                if option.state & QStyle.StateFlag.State_Selected
                else option.palette.text().color()
            )
            painter.drawText(option.rect.adjusted(4, 0, -4, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def helpEvent(self, event, view, option, index):
        if (event.type() == event.Type.ToolTip and index.isValid()
                and index.column() == ProjectTableModel.NameCol):
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            fm = option.fontMetrics
            elided = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, option.rect.width() - 8)
            if elided != text:
                QToolTip.showText(event.globalPos(), text)
                return True
        return super().helpEvent(event, view, option, index)
