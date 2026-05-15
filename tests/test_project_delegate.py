"""ProjectDelegate 列表行渲染测试。"""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtWidgets import QStyleOptionViewItem

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import BUILTIN_STAGE_NAMES, Project, ProjectStage
from civ_core.infra_io.project_db import ProjectDB
from civ_core.ui.components.project_delegate import ProjectDelegate
from civ_core.ui.models.project_list_model import ProjectListModel


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


@pytest.fixture
def svc() -> ProjectService:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    return ProjectService(db)


@pytest.fixture
def model(svc: ProjectService) -> ProjectListModel:
    svc.create_project(_project(project_number="P001"), create_folder=False)
    svc.create_project(_project(project_number="P002"), create_folder=False)
    return ProjectListModel(svc)


@pytest.fixture
def delegate() -> ProjectDelegate:
    return ProjectDelegate()


class TestSizeHint:
    def test_returns_44px_height(
        self, delegate: ProjectDelegate, model: ProjectListModel
    ) -> None:
        size = delegate.sizeHint(QStyleOptionViewItem(), model.index(0))
        assert size.height() == 44

    def test_width_is_zero(
        self, delegate: ProjectDelegate, model: ProjectListModel
    ) -> None:
        size = delegate.sizeHint(QStyleOptionViewItem(), model.index(0))
        assert size.width() == 0


class TestRowHeight:
    def test_row_height_constant(self, delegate: ProjectDelegate) -> None:
        assert delegate.row_height() == 44


class TestConstructible:
    def test_create_without_parent(self) -> None:
        d = ProjectDelegate()
        assert d is not None
        assert d.row_height() == 44
