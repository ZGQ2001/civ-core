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
from PySide6.QtGui import QFont

from civ_core.core.project_service import ProjectService
from civ_core.infra_io.style_loader import load_style_preset

HEADERS = ["状态", "编号", "项目名称", "类型", "金额", "日期", "进度"]

# 自定义 SortRole（避开 Qt 内置 Display / Edit / UserRole）。
# 必须大于 UserRole(0x100)。proxy.setSortRole(SortRole) 用此值。
SortRole = Qt.ItemDataRole.UserRole + 100


def _mono_font() -> QFont:
    """从 style_preset 取等宽字体（用于数据列）。

    备选族写在 yaml 里（'JetBrains Mono', 'Consolas', monospace），
    Qt 会按顺序回退到第一个可用的本地字体。
    """
    sty = load_style_preset()
    f = QFont()
    # setFamilies 接受备选列表；解析 yaml 里的逗号分隔字符串
    families = [s.strip().strip("'\"") for s in sty.typography.font_family_mono.split(",")]
    f.setFamilies(families)
    f.setPointSize(sty.typography.size_body)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


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

        elif role == Qt.ItemDataRole.FontRole:
            # 数据列用等宽字体确保数字 / 编号 / 日期对齐
            if col in (self.NumberCol, self.AmountCol, self.DateCol, self.ProgressCol):
                return _mono_font()
            return None

        elif role == Qt.ItemDataRole.UserRole:
            return p  # 返回完整 Project 对象

        elif role == SortRole:
            # 排序专用：返回未格式化的原始值（datetime / float / int / str），
            # 让 QSortFilterProxyModel.lessThan 直接比较。
            if col == self.StatusCol:
                # 状态权重：未开始 0 / 进行中 1 / 全完成 2
                if p.is_all_completed:
                    return 2
                if p.completed_stage_count > 0 or p.in_progress_count > 0:
                    return 1
                return 0
            if col == self.NumberCol:
                return p.project_number
            if col == self.NameCol:
                return p.name
            if col == self.TypeCol:
                return p.inspection_type
            if col == self.AmountCol:
                return float(p.amount)
            if col == self.DateCol:
                return p.created_at  # datetime 直接可比较
            if col == self.ProgressCol:
                return int(p.completed_stage_count)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.StatusCol:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section] if 0 <= section < len(HEADERS) else None
        return None
