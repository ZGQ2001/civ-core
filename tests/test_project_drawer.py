"""ProjectDrawer 滑出面板测试。"""

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
from civ_core.ui.components.project_drawer import ProjectDrawer


def _stages() -> tuple[ProjectStage, ...]:
    return tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)


def _project(**overrides: object) -> Project:
    kwargs: dict[str, object] = {
        "project_number": "P001", "name": "测试项目",
        "client": "甲方", "inspection_type": "类型A",
        "amount": 100.0, "stages": _stages(), "project_id": 1,
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


class TestDrawerConstruct:
    def test_creates_without_crash(self, qapp: QApplication) -> None:
        drawer = ProjectDrawer()
        assert drawer._stack is not None

    def test_set_project_shows_summary(self, qapp: QApplication) -> None:
        drawer = ProjectDrawer()
        drawer.set_project(_project(), None)
        assert drawer._stack.currentIndex() == 0

    def test_switch_edit_back(self, qapp: QApplication, svc: ProjectService) -> None:
        drawer = ProjectDrawer()
        drawer.set_project(_project(), svc)
        drawer._show_edit_page()
        assert drawer._stack.currentIndex() == 1
        drawer._show_summary_page()
        assert drawer._stack.currentIndex() == 0


class TestAnimation:
    def test_open_creates_animation(self, qapp: QApplication) -> None:
        drawer = ProjectDrawer()
        drawer.set_project(_project(), None)
        drawer.open()
        assert drawer._animation is not None

    def test_close_animates_to_zero(self, qapp: QApplication) -> None:
        drawer = ProjectDrawer()
        drawer.set_project(_project(), None)
        drawer.open()
        drawer.close()
        assert drawer._animation is not None
