"""project_service 业务逻辑层测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from civ_core.core.project_service import ProjectService
from civ_core.domain.project_schema import (
    BUILTIN_STAGE_NAMES,
    Project,
    ProjectStage,
    StageStatus,
)
from civ_core.infra_io.project_db import ProjectDB


@pytest.fixture
def svc() -> ProjectService:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    return ProjectService(db)


def _new_stages() -> tuple[ProjectStage, ...]:
    return tuple(ProjectStage(name=n) for n in BUILTIN_STAGE_NAMES)


def _new_project(**overrides: object) -> Project:
    kwargs: dict[str, object] = {
        "project_number": "P2024001",
        "name": "小米基地检测",
        "client": "小米集团",
        "inspection_type": "施工质量评价",
        "amount": 186000.0,
        "stages": _new_stages(),
        "project_id": 0,
    }
    kwargs.update(overrides)
    return Project(**kwargs)  # type: ignore[arg-type]


class TestCreateProject:
    @patch("civ_core.core.project_service.create_project_folder")
    def test_returns_project_with_id(self, mock_create, svc: ProjectService) -> None:
        mock_create.return_value = Path("D:/Projects/20260515-P2024001-小米基地检测")
        p = _new_project()
        result = svc.create_project(
            p, folder_parent=Path("D:/Projects"), date_str="20260515"
        )
        assert result.project_id > 0
        assert result.project_number == "P2024001"
        mock_create.assert_called_once()

    @patch("civ_core.core.project_service.create_project_folder")
    def test_auto_creates_folder(self, mock_create, svc: ProjectService) -> None:
        mock_create.return_value = Path("D:/Projects/20260515-P2024001-测试")
        svc.create_project(
            _new_project(), folder_parent=Path("D:/Projects"), date_str="20260515"
        )
        mock_create.assert_called_once()

    @patch("civ_core.core.project_service.create_project_folder")
    def test_folder_path_none_skips_creation(self, mock_create, svc: ProjectService) -> None:
        svc.create_project(_new_project(), create_folder=False)
        mock_create.assert_not_called()

    @patch("civ_core.core.project_service.create_project_folder")
    def test_duplicate_number_raises(self, mock_create, svc: ProjectService) -> None:
        mock_create.return_value = Path("D:/Projects/20260515-P2024001-测试")
        svc.create_project(
            _new_project(), folder_parent=Path("D:/Projects"), date_str="20260515"
        )
        with pytest.raises(ValueError, match="重复"):
            svc.create_project(
                _new_project(), folder_parent=Path("D:/Projects"), date_str="20260515"
            )


class TestGetProject:
    def test_returns_existing(self, svc: ProjectService) -> None:
        inserted = svc.create_project(_new_project(), create_folder=False)
        fetched = svc.get_project(inserted.project_id)
        assert fetched.project_id == inserted.project_id

    def test_raises_not_found(self, svc: ProjectService) -> None:
        with pytest.raises(ValueError, match="不存在"):
            svc.get_project(999)


class TestListProjects:
    def test_empty(self, svc: ProjectService) -> None:
        assert svc.list_projects() == []

    def test_returns_all(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001"), create_folder=False)
        svc.create_project(_new_project(project_number="P002"), create_folder=False)
        assert len(svc.list_projects()) == 2


class TestUpdateStage:
    def test_updates_stage_status(self, svc: ProjectService) -> None:
        inserted = svc.create_project(_new_project(), create_folder=False)
        result = svc.update_stage(inserted.project_id, "现场检测", StageStatus.COMPLETED, note="完成")
        assert result.stages[0].status == StageStatus.COMPLETED


class TestDeleteProject:
    def test_deletes_and_returns_true(self, svc: ProjectService) -> None:
        inserted = svc.create_project(_new_project(), create_folder=False)
        assert svc.delete_project(inserted.project_id) is True
        with pytest.raises(ValueError, match="不存在"):
            svc.get_project(inserted.project_id)

    def test_not_found_returns_false(self, svc: ProjectService) -> None:
        assert svc.delete_project(999) is False


class TestArchiveProject:
    def test_marks_all_completed(self, svc: ProjectService) -> None:
        inserted = svc.create_project(_new_project(), create_folder=False)
        result = svc.archive_project(inserted.project_id)
        assert result.is_all_completed is True


class TestFilterProjects:
    """4 档筛选：全部 / 正在进行 / 暂存 / 已归档（严格互斥）。

    判定规则（优先级从高到低）：
      已归档 = is_archived
      暂存   = is_on_hold AND NOT is_archived
      正在进行 = NOT is_on_hold AND NOT is_archived
    """

    def test_all_returns_everything(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001"), create_folder=False)
        p2 = svc.create_project(_new_project(project_number="P002"), create_folder=False)
        svc.set_on_hold(p2.project_id, True)
        assert len(svc.filter_projects("全部")) == 2

    def test_active_excludes_on_hold_and_archived(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001"), create_folder=False)
        p2 = svc.create_project(_new_project(project_number="P002"), create_folder=False)
        p3 = svc.create_project(_new_project(project_number="P003"), create_folder=False)
        svc.set_on_hold(p2.project_id, True)
        svc.set_archived(p3.project_id, True)
        result = svc.filter_projects("正在进行")
        assert len(result) == 1
        assert result[0].project_number == "P001"

    def test_on_hold_filter(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001"), create_folder=False)
        p2 = svc.create_project(_new_project(project_number="P002"), create_folder=False)
        svc.set_on_hold(p2.project_id, True)
        result = svc.filter_projects("暂存")
        assert len(result) == 1
        assert result[0].project_number == "P002"

    def test_archived_filter(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001"), create_folder=False)
        p2 = svc.create_project(_new_project(project_number="P002"), create_folder=False)
        svc.set_archived(p2.project_id, True)
        result = svc.filter_projects("已归档")
        assert len(result) == 1
        assert result[0].project_number == "P002"

    def test_archived_takes_priority_over_on_hold(self, svc: ProjectService) -> None:
        # 同时 is_on_hold + is_archived → 归档优先，不算暂存
        p = svc.create_project(_new_project(project_number="P001"), create_folder=False)
        svc.set_on_hold(p.project_id, True)
        svc.set_archived(p.project_id, True)
        assert len(svc.filter_projects("已归档")) == 1
        assert len(svc.filter_projects("暂存")) == 0


class TestStatusFlagWrappers:
    """set_on_hold / set_archived service wrapper。"""

    def test_set_on_hold_true(self, svc: ProjectService) -> None:
        p = svc.create_project(_new_project(), create_folder=False)
        result = svc.set_on_hold(p.project_id, True)
        assert result.is_on_hold is True

    def test_set_archived_true(self, svc: ProjectService) -> None:
        p = svc.create_project(_new_project(), create_folder=False)
        result = svc.set_archived(p.project_id, True)
        assert result.is_archived is True

    def test_set_on_hold_not_found_raises(self, svc: ProjectService) -> None:
        with pytest.raises(ValueError):
            svc.set_on_hold(999, True)

    def test_set_archived_not_found_raises(self, svc: ProjectService) -> None:
        with pytest.raises(ValueError):
            svc.set_archived(999, True)


class TestStatistics:
    def test_empty_stats(self, svc: ProjectService) -> None:
        stats = svc.get_statistics()
        assert stats["total"] == 0

    def test_with_projects(self, svc: ProjectService) -> None:
        svc.create_project(_new_project(project_number="P001", amount=100.0), create_folder=False)
        svc.create_project(_new_project(project_number="P002", amount=200.0), create_folder=False)
        stats = svc.get_statistics()
        assert stats["total"] == 2
        assert stats["total_amount"] == 300.0
