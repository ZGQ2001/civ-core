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


class TestStatusFlagToggles:
    """暂存/归档按钮：点击 → 调 service 切换 → 按钮态同步。"""

    def test_buttons_exist_after_set_project(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        drawer = ProjectDrawer()
        drawer.set_project(inserted, svc)
        assert drawer._btn_on_hold is not None
        assert drawer._btn_archived is not None

    def test_initial_state_unchecked(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        drawer = ProjectDrawer()
        drawer.set_project(inserted, svc)
        assert drawer._btn_on_hold.isChecked() is False
        assert drawer._btn_archived.isChecked() is False

    def test_initial_state_reflects_project_flags(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        svc.set_on_hold(inserted.project_id, True)
        updated = svc.get_project(inserted.project_id)
        drawer = ProjectDrawer()
        drawer.set_project(updated, svc)
        assert drawer._btn_on_hold.isChecked() is True
        assert drawer._btn_archived.isChecked() is False

    def test_toggle_on_hold_persists(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        drawer = ProjectDrawer()
        drawer.set_project(inserted, svc)
        drawer._toggle_on_hold()
        reloaded = svc.get_project(inserted.project_id)
        assert reloaded.is_on_hold is True

    def test_toggle_archived_persists(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        drawer = ProjectDrawer()
        drawer.set_project(inserted, svc)
        drawer._toggle_archived()
        reloaded = svc.get_project(inserted.project_id)
        assert reloaded.is_archived is True

    def test_toggle_on_hold_off(self, qapp: QApplication, svc: ProjectService) -> None:
        inserted = svc.create_project(_project(), create_folder=False)
        svc.set_on_hold(inserted.project_id, True)
        drawer = ProjectDrawer()
        drawer.set_project(svc.get_project(inserted.project_id), svc)
        drawer._toggle_on_hold()  # True -> False
        reloaded = svc.get_project(inserted.project_id)
        assert reloaded.is_on_hold is False


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
