"""ProjectListModel：MVC 架构的 Model 层，包装 Project 列表供 QListView 渲染。

每个 UserRole 映射到 Project 的一个字段，供 Delegate 的 paint() 直接获取。
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from civ_core.core.project_service import ProjectService

# 统一列宽 + 左边距
LEFT_PADDING = 16
COL_WIDTHS: dict[str, int] = {
    "status":    24,   # 状态圆点
    "dot_pad":   10,   # 圆点后留白
    "number":    72,   # 项目编号
    "name":      200,  # 项目名称
    "type":      90,   # 检测类型
    "amount":    80,   # 金额
    "date":      90,   # 创建日期 (YYYY-MM-DD)
    "progress":  84,   # 进度条 + 文字
}

class ProjectListModel(QAbstractListModel):
    """项目列表数据模型。

    角色定义（Qt.UserRole + 偏移）：
      ProjectNumberRole — project_number 字符串
      NameRole          — name 字符串
      ClientRole        — client 字符串
      InspectionTypeRole — inspection_type 字符串
      AmountRole        — amount float
      ProgressRole      — "3/7" 进度字符串
      ProjectObjectRole — 完整 Project dataclass（供 Drawer 使用）
    """

    ProjectNumberRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    ClientRole = Qt.ItemDataRole.UserRole + 3
    InspectionTypeRole = Qt.ItemDataRole.UserRole + 4
    AmountRole = Qt.ItemDataRole.UserRole + 5
    ProgressRole = Qt.ItemDataRole.UserRole + 6
    DateRole = Qt.ItemDataRole.UserRole + 8
    ProjectObjectRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, service: ProjectService, parent=None):
        super().__init__(parent)
        self.service = service
        self._projects: list = []
        self.refresh()

    def refresh(self) -> None:
        """重新从 DB 加载全量数据并通知视图。"""
        self.beginResetModel()
        self._projects = self.service.list_projects()
        self.endResetModel()

    # ── QAbstractListModel 接口 ────────────────────────────────
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._projects)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._projects):
            return None

        proj = self._projects[row]

        if role == Qt.ItemDataRole.DisplayRole:
            return proj.name
        elif role == self.ProjectNumberRole:
            return proj.project_number
        elif role == self.NameRole:
            return proj.name
        elif role == self.ClientRole:
            return proj.client
        elif role == self.InspectionTypeRole:
            return proj.inspection_type
        elif role == self.AmountRole:
            return proj.amount
        elif role == self.ProgressRole:
            return f"{proj.completed_stage_count}/7"
        elif role == self.DateRole:
            return proj.created_at.strftime("%Y-%m-%d") if proj.created_at else ""
        elif role == self.ProjectObjectRole:
            return proj
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
