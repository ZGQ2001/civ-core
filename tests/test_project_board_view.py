"""ProjectBoardView 主页组装测试。"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import (
    BUILTIN_STAGE_NAMES,
    Project,
    ProjectStage,
)
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.windows.project_board_view import ProjectBoardView


def _stages() -> tuple[ProjectStage, ...]:
    return tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)


def _project(**overrides: object) -> Project:
    kwargs: dict[str, object] = {
        "project_number": "P001", "name": "测试",
        "client": "甲方", "inspection_type": "类型A",
        "amount": 100.0, "stages": _stages(), "project_id": 0,
    }
    kwargs.update(overrides)
    return Project(**kwargs)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture
def svc() -> ProjectService:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    return ProjectService(db)


class TestBoardViewConstruct:
    def test_create_view(self, qapp: QApplication, svc: ProjectService) -> None:
        view = ProjectBoardView(svc)
        assert view._table_view is not None
        assert view._board_widget is not None
        assert view._drawer is not None

    def test_default_list_view(self, qapp: QApplication, svc: ProjectService) -> None:
        view = ProjectBoardView(svc)
        assert view._view_stack.currentIndex() == 0

    def test_switch_to_board(self, qapp: QApplication, svc: ProjectService) -> None:
        view = ProjectBoardView(svc)
        view._switch_to_board()
        assert view._view_stack.currentIndex() == 1

    def test_filter(self, qapp: QApplication, svc: ProjectService) -> None:
        svc.create_project(_project(project_number="P001"), create_folder=False)
        svc.create_project(_project(project_number="P002"), create_folder=False)
        view = ProjectBoardView(svc)
        view._on_filter_changed("团队积压")
        assert view._model.rowCount() == 2

    def test_btn_new_exists(self, qapp: QApplication, svc: ProjectService) -> None:
        view = ProjectBoardView(svc)
        assert view._btn_new is not None


class TestDrawerClose:
    """drawer 关闭路径：open → close 必须把 splitter 第二格收到 0。

    历史 bug：setChildrenCollapsible(False) 阻止程序化塌缩，drawer 关不掉。
    """

    def test_close_collapses_drawer_to_zero(
        self, qapp: QApplication, svc: ProjectService
    ) -> None:
        # 构造项目 + view，并把窗口给一个合理尺寸（保证 splitter 有非零总宽）
        proj = svc.create_project(_project(project_number="P001"), create_folder=False)
        view = ProjectBoardView(svc)
        view.resize(1200, 700)
        view.show()
        qapp.processEvents()

        # 打开 drawer
        view._open_drawer_for(proj)
        qapp.processEvents()
        assert view._body_splitter.sizes()[1] > 0, "drawer 打开后应有正宽度"

        # 关闭 drawer → 第二格必须为 0
        view._drawer.close()
        qapp.processEvents()
        assert view._body_splitter.sizes()[1] == 0, (
            f"drawer 关闭后宽度应为 0，实际 {view._body_splitter.sizes()}"
        )
        view.close()
