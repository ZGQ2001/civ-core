"""ProjectBoardWidget 3列看板测试。"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import (
    BUILTIN_STAGE_NAMES,
    Project,
    ProjectStage,
    StageStatus,
)
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.components.project_board_widget import ProjectBoardWidget


def _stages(status: StageStatus = StageStatus.NOT_STARTED) -> tuple[ProjectStage, ...]:
    return tuple(ProjectStage(name=n, status=status) for n in BUILTIN_STAGE_NAMES)


def _project(**overrides: object) -> Project:
    kwargs: dict[str, object] = {
        "project_number": "P001", "name": "测试",
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


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


class TestBoardConstruct:
    def test_creates_three_columns(self, qapp: QApplication) -> None:
        widget = ProjectBoardWidget()
        assert widget._pending_column is not None
        assert widget._in_progress_column is not None
        assert widget._completed_column is not None

    def test_refresh_no_projects(self, qapp: QApplication, svc: ProjectService) -> None:
        widget = ProjectBoardWidget()
        widget.set_service(svc)
        widget.refresh()  # 不应抛异常

    def test_refresh_sorts_projects(self, qapp: QApplication, svc: ProjectService) -> None:
        # Pending: all NOT_STARTED
        svc.create_project(_project(project_number="P001"), create_folder=False)
        # In-progress: 1 stage completed
        p2 = svc.create_project(_project(project_number="P002"), create_folder=False)
        svc.update_stage(p2.project_id, "现场检测", StageStatus.COMPLETED)
        # Completed: all completed
        svc.create_project(_project(project_number="P003", stages=_stages(StageStatus.COMPLETED)), create_folder=False)

        widget = ProjectBoardWidget()
        widget.set_service(svc)
        widget.refresh()

        # 验证三列分别有 1 个项目
        assert len(widget._pending_items) == 1
        assert len(widget._in_progress_items) == 1
        assert len(widget._completed_items) == 1


class TestColumnTitles:
    def test_column_titles_have_count_format(self, qapp: QApplication, svc: ProjectService) -> None:
        svc.create_project(_project(project_number="P001"), create_folder=False)
        widget = ProjectBoardWidget()
        widget.set_service(svc)
        widget.refresh()
        # 待处理列标题应含 "(1)"
        pending_title = widget._pending_column.title_label.text()
        assert "(1)" in pending_title
