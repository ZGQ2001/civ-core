"""ProjectTableModel：QAbstractTableModel，供 QTableView 全局只读渲染。

列定义（7 列）：
  0: status   状态圆点（○/●/✓）
  1: number   项目编号
  2: name     项目名称
  3: type     检测类型
  4: amount   金额
  5: date     创建日期 YYYY-MM-DD
  6: progress 进度 "3/7"
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from civ_core.core.project_service import ProjectService

HEADERS = ["状态", "编号", "项目名称", "类型", "金额", "日期", "进度"]


class ProjectTableModel(QAbstractTableModel):
    """项目表格模型（只读）。"""

    StatusCol = 0
    NumberCol = 1
    NameCol = 2
    TypeCol = 3
    AmountCol = 4
    DateCol = 5
    ProgressCol = 6

    def __init__(self, service: ProjectService, parent=None):
        super().__init__(parent)
        self._service = service
        self._projects: list = []
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._projects = self._service.list_projects()
        self.endResetModel()

    # ── QAbstractTableModel ───────────────────────────────────
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._projects)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 7 if not parent.isValid() else 0

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        p = self._projects[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.StatusCol:
                if p.is_all_completed:
                    return "✓"
                elif p.completed_stage_count > 0 or p.in_progress_count > 0:
                    return "●"
                return "○"
            elif col == self.NumberCol:
                return p.project_number
            elif col == self.NameCol:
                return p.name
            elif col == self.TypeCol:
                return p.inspection_type
            elif col == self.AmountCol:
                return f"¥{p.amount:,.0f}"
            elif col == self.DateCol:
                return p.created_at.strftime("%Y-%m-%d") if p.created_at else ""
            elif col == self.ProgressCol:
                return f"{p.completed_stage_count}/7"

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == self.StatusCol:
                if p.is_all_completed:
                    return Qt.GlobalColor.green
                elif p.completed_stage_count > 0 or p.in_progress_count > 0:
                    return Qt.GlobalColor.blue
                return Qt.GlobalColor.gray
            elif col == self.AmountCol:
                return Qt.GlobalColor.darkBlue
            elif col == self.DateCol:
                return Qt.GlobalColor.darkGray

        elif role == Qt.ItemDataRole.UserRole:
            return p  # 返回完整 Project 对象

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.StatusCol:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section] if 0 <= section < len(HEADERS) else None
        return None
