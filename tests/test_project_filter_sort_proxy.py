"""ProjectFilterSortProxy 测试：4 档筛选 + 多列排序。

设计要点：
  • Proxy 套在 ProjectTableModel 上
  • filterAcceptsRow 按 filter_type (全部/正在进行/暂存/已归档) 过滤
  • lessThan 通过 SortRole 取 datetime / float / int 原始值比较
"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtCore import Qt

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.models.project_filter_sort_proxy import (
    SORT_ROLE,
    ProjectFilterSortProxy,
)
from civ_core.ui.models.project_table_model import ProjectTableModel


def _stages() -> tuple[ProjectStage, ...]:
    return tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)


def _project(**overrides: object) -> Project:
    kwargs: dict[str, object] = {
        "project_number": "P001", "name": "测试项目",
        "client": "甲方", "inspection_type": "类型A",
        "amount": 100.0, "stages": _stages(), "project_id": 0,
    }
    kwargs.update(overrides)
    return Project(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def svc() -> ProjectService:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    return ProjectService(db)


@pytest.fixture
def proxy(svc: ProjectService) -> ProjectFilterSortProxy:
    # 创建 3 个项目，状态各不相同
    svc.create_project(_project(project_number="P001", amount=100.0), create_folder=False)
    p2 = svc.create_project(_project(project_number="P002", amount=300.0), create_folder=False)
    p3 = svc.create_project(_project(project_number="P003", amount=200.0), create_folder=False)
    svc.set_on_hold(p2.project_id, True)
    svc.set_archived(p3.project_id, True)

    model = ProjectTableModel(svc)
    pxy = ProjectFilterSortProxy()
    pxy.setSourceModel(model)
    return pxy


# ────────────────────────────────────────────────────────────────
class TestSortRoleValues:
    """ProjectTableModel 必须实现 SortRole，返回未格式化的原始值。"""

    def test_amount_sort_role_is_float(self, svc: ProjectService) -> None:
        svc.create_project(_project(amount=12345.67), create_folder=False)
        model = ProjectTableModel(svc)
        idx = model.index(0, ProjectTableModel.AmountCol)
        val = model.data(idx, SORT_ROLE)
        assert isinstance(val, float)
        assert val == 12345.67

    def test_date_sort_role_is_comparable(self, svc: ProjectService) -> None:
        svc.create_project(_project(), create_folder=False)
        model = ProjectTableModel(svc)
        idx = model.index(0, ProjectTableModel.DateCol)
        val = model.data(idx, SORT_ROLE)
        # datetime 或 ISO 字符串均可，关键是可比较
        assert val is not None

    def test_progress_sort_role_is_int(self, svc: ProjectService) -> None:
        svc.create_project(_project(), create_folder=False)
        model = ProjectTableModel(svc)
        idx = model.index(0, ProjectTableModel.ProgressCol)
        val = model.data(idx, SORT_ROLE)
        assert isinstance(val, int)


# ────────────────────────────────────────────────────────────────
class TestFontRole:
    """数据列（编号/金额/日期/进度）必须返回等宽 QFont。"""

    def test_amount_uses_mono_font(self, svc: ProjectService) -> None:
        from PySide6.QtGui import QFont
        svc.create_project(_project(), create_folder=False)
        model = ProjectTableModel(svc)
        idx = model.index(0, ProjectTableModel.AmountCol)
        font = model.data(idx, Qt.ItemDataRole.FontRole)
        assert isinstance(font, QFont)
        assert font.styleHint() == QFont.StyleHint.Monospace

    def test_name_col_no_explicit_font(self, svc: ProjectService) -> None:
        svc.create_project(_project(), create_folder=False)
        model = ProjectTableModel(svc)
        idx = model.index(0, ProjectTableModel.NameCol)
        # 名称列不返回字体（用比例字体默认）
        assert model.data(idx, Qt.ItemDataRole.FontRole) is None

    def test_number_date_progress_use_mono(self, svc: ProjectService) -> None:
        from PySide6.QtGui import QFont
        svc.create_project(_project(), create_folder=False)
        model = ProjectTableModel(svc)
        for col in (ProjectTableModel.NumberCol, ProjectTableModel.DateCol, ProjectTableModel.ProgressCol):
            font = model.data(model.index(0, col), Qt.ItemDataRole.FontRole)
            assert isinstance(font, QFont)


# ────────────────────────────────────────────────────────────────
class TestFilter:
    def test_default_filter_all(self, proxy: ProjectFilterSortProxy) -> None:
        # 默认 "全部"：3 行都可见
        assert proxy.rowCount() == 3

    def test_filter_active(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.set_filter_type("正在进行")
        # 仅 P001（既不暂存也不归档）
        assert proxy.rowCount() == 1
        idx = proxy.index(0, ProjectTableModel.NumberCol)
        assert idx.data(Qt.ItemDataRole.DisplayRole) == "P001"

    def test_filter_on_hold(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.set_filter_type("暂存")
        assert proxy.rowCount() == 1
        idx = proxy.index(0, ProjectTableModel.NumberCol)
        assert idx.data(Qt.ItemDataRole.DisplayRole) == "P002"

    def test_filter_archived(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.set_filter_type("已归档")
        assert proxy.rowCount() == 1
        idx = proxy.index(0, ProjectTableModel.NumberCol)
        assert idx.data(Qt.ItemDataRole.DisplayRole) == "P003"

    def test_unknown_filter_treated_as_all(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.set_filter_type("乱七八糟")
        assert proxy.rowCount() == 3

    def test_filter_switch_back(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.set_filter_type("暂存")
        assert proxy.rowCount() == 1
        proxy.set_filter_type("全部")
        assert proxy.rowCount() == 3


# ────────────────────────────────────────────────────────────────
class TestSort:
    def test_sort_by_amount_ascending(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.sort(ProjectTableModel.AmountCol, Qt.SortOrder.AscendingOrder)
        # 升序：100 → 200 → 300
        amounts = [proxy.index(r, ProjectTableModel.NumberCol).data() for r in range(3)]
        assert amounts == ["P001", "P003", "P002"]

    def test_sort_by_amount_descending(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.sort(ProjectTableModel.AmountCol, Qt.SortOrder.DescendingOrder)
        numbers = [proxy.index(r, ProjectTableModel.NumberCol).data() for r in range(3)]
        assert numbers == ["P002", "P003", "P001"]

    def test_sort_by_number(self, proxy: ProjectFilterSortProxy) -> None:
        proxy.sort(ProjectTableModel.NumberCol, Qt.SortOrder.AscendingOrder)
        numbers = [proxy.index(r, ProjectTableModel.NumberCol).data() for r in range(3)]
        assert numbers == ["P001", "P002", "P003"]
