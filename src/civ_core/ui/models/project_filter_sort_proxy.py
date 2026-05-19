"""ProjectFilterSortProxy：QSortFilterProxyModel 子类。

合并 4 档筛选 + 多列排序两件事，原因：
  • 表格只有一个 setModel(proxy) 接口，分两层 proxy 会让信号链复杂化
  • filter 与 sort 都按行级判断，公用 sourceModel 索引

用法：
    proxy = ProjectFilterSortProxy()
    proxy.setSourceModel(project_table_model)
    table_view.setModel(proxy)
    table_view.setSortingEnabled(True)
    proxy.sort(DateCol, Qt.DescendingOrder)
    proxy.set_filter_type("正在进行")
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from civ_core.domain.project_schema import Project
from civ_core.ui.models.project_table_model import SortRole

# 暴露 SORT_ROLE 供 view 层 setSortRole 用
SORT_ROLE = SortRole

# 4 档筛选名（与 service.filter_projects 保持一致）
FILTER_ALL = "全部"
FILTER_ACTIVE = "正在进行"
FILTER_ON_HOLD = "暂存"
FILTER_ARCHIVED = "已归档"
VALID_FILTERS = (FILTER_ALL, FILTER_ACTIVE, FILTER_ON_HOLD, FILTER_ARCHIVED)


class ProjectFilterSortProxy(QSortFilterProxyModel):
    """4 档筛选 + 多列排序（使用 SortRole 拿原始值，避免字符串比较坑）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_type: str = FILTER_ALL
        # 关键：让 QSortFilterProxyModel 拿 SortRole 的值参与 lessThan
        self.setSortRole(SORT_ROLE)
        # 我们的 filterAcceptsRow 不依赖 filterRegExp，直接判断 Project 对象
        self.setDynamicSortFilter(True)

    # ── 筛选 API ────────────────────────────────────────────────
    def set_filter_type(self, filter_type: str) -> None:
        """切换 4 档筛选；未知值降级为 '全部'。"""
        self._filter_type = filter_type if filter_type in VALID_FILTERS else FILTER_ALL
        # invalidate() 是通用入口，不会触发 PySide6 不同版本的 deprecated 警告
        self.invalidate()

    def filter_type(self) -> str:
        return self._filter_type

    # ── QSortFilterProxyModel 钩子 ─────────────────────────────
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """按 4 档规则判断是否保留行。规则与 service.filter_projects 完全一致。"""
        if self._filter_type == FILTER_ALL:
            return True

        src = self.sourceModel()
        idx = src.index(source_row, 0, source_parent)
        proj = src.data(idx, Qt.ItemDataRole.UserRole)
        if not isinstance(proj, Project):
            return True  # 不认识的行不过滤掉，安全兜底

        if self._filter_type == FILTER_ARCHIVED:
            return proj.is_archived
        if self._filter_type == FILTER_ON_HOLD:
            return proj.is_on_hold and not proj.is_archived
        if self._filter_type == FILTER_ACTIVE:
            return not proj.is_on_hold and not proj.is_archived
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """用 SortRole 取原始值比较；任一侧为 None 时按 Qt 默认行为。"""
        lval = left.data(SORT_ROLE)
        rval = right.data(SORT_ROLE)
        if lval is None and rval is None:
            return False
        if lval is None:
            return True
        if rval is None:
            return False
        try:
            return lval < rval
        except TypeError:
            # 类型不兼容时回退到字符串比较
            return str(lval) < str(rval)
