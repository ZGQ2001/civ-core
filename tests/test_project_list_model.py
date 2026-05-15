"""ProjectListModel QAbstractListModel 测试。"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtCore import Qt

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.models.project_list_model import ProjectListModel


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
def model() -> ProjectListModel:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    svc = ProjectService(db)
    svc.create_project(_project(project_number="P001"), create_folder=False)
    svc.create_project(_project(project_number="P002"), create_folder=False)
    return ProjectListModel(svc)


class TestRowCount:
    def test_returns_project_count(self, model: ProjectListModel) -> None:
        assert model.rowCount() == 2

    def test_refresh_updates_count(self, model: ProjectListModel) -> None:
        model.service.create_project(
            _project(project_number="P003"), create_folder=False
        )
        model.refresh()
        assert model.rowCount() == 3


class TestDataRoles:
    def test_display_returns_name(self, model: ProjectListModel) -> None:
        index = model.index(0)
        text = model.data(index, Qt.ItemDataRole.DisplayRole)
        assert "测试项目" in text

    def test_user_role_project_number(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        assert "P" in model.data(idx, ProjectListModel.ProjectNumberRole)

    def test_user_role_name(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        assert model.data(idx, ProjectListModel.NameRole) == "测试项目"

    def test_user_role_client(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        assert model.data(idx, ProjectListModel.ClientRole) == "甲方"

    def test_user_role_amount(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        assert model.data(idx, ProjectListModel.AmountRole) == 100.0

    def test_user_role_progress_count(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        assert model.data(idx, ProjectListModel.ProgressRole) == "0/7"

    def test_user_role_project_obj(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        proj = model.data(idx, ProjectListModel.ProjectObjectRole)
        assert isinstance(proj, Project)
        assert proj.project_number == "P002"


class TestFlags:
    def test_item_is_selectable_and_enabled(self, model: ProjectListModel) -> None:
        idx = model.index(0)
        flags = model.flags(idx)
        assert flags & Qt.ItemFlag.ItemIsSelectable
        assert flags & Qt.ItemFlag.ItemIsEnabled


class TestEmptyModel:
    def test_row_count_zero(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db = ProjectDB(conn)
        db.create_tables()
        svc = ProjectService(db)
        model = ProjectListModel(svc)
        assert model.rowCount() == 0
