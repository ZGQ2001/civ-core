"""project_db SQLite CRUD 测试。

测试覆盖：
  - 建表幂等性
  - insert_project → 自动生成 project_id + 7 条 stage 记录
  - get_project → 从 DB 重建完整 Project（含 7 阶段）
  - list_projects → 全量加载
  - update_project → 更新业务字段（不碰 stages）
  - update_stage → 更新单阶段状态 + note + updated_at
  - delete_project → 级联删除 stages
  - archive_project → 全阶段标记 COMPLETED
  - 编号唯一性约束
  - 临时文件隔离（:memory: / tmpdir），不碰真实 DB
"""

from __future__ import annotations

import sqlite3

import pytest

from civ_core.domain.project_schema import (
    BUILTIN_STAGE_NAMES,
    Project,
    ProjectStage,
    StageStatus,
)
from civ_core.infra_io.project_db import (
    ProjectDB,
    ProjectNotFoundError,
)


@pytest.fixture
def db() -> ProjectDB:
    """每个测试独立的 :memory: DB。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = ProjectDB(conn)
    db.create_tables()
    return db


# ── helpers ──────────────────────────────────────────────────────
def _new_project_stages() -> tuple[ProjectStage, ...]:
    return tuple(
        ProjectStage(name=n, status=StageStatus.NOT_STARTED)
        for n in BUILTIN_STAGE_NAMES
    )


def _new_project(**overrides: object) -> Project:
    """构造一个新建项目（不含 project_id）。"""
    kwargs: dict[str, object] = {
        "project_number": "P2024001",
        "name": "小米智能制造产业基地施工质量评价",
        "client": "小米集团",
        "inspection_type": "施工质量评价",
        "amount": 186000.0,
        "stages": _new_project_stages(),
        "project_id": 0,  # 新建，未分配
    }
    kwargs.update(overrides)
    return Project(**kwargs)  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────
class TestCreateTables:
    def test_idempotent(self, db: ProjectDB) -> None:
        # 第一次建表成功
        # create_tables 已在 fixture 中调用 → 再次调用不抛异常
        db.create_tables()  # 幂等

    def test_tables_exist(self, db: ProjectDB) -> None:
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('projects', 'project_stages')"
        )
        tables = {row[0] for row in cur.fetchall()}
        assert tables == {"projects", "project_stages"}


# ────────────────────────────────────────────────────────────────
class TestInsertProject:
    def test_insert_returns_project_with_id(self, db: ProjectDB) -> None:
        p = _new_project()
        result = db.insert_project(p)
        assert result.project_id > 0
        assert result.project_number == p.project_number
        assert len(result.stages) == 7

    def test_insert_creates_seven_stages(self, db: ProjectDB) -> None:
        p = _new_project()
        result = db.insert_project(p)
        assert len(result.stages) == 7
        for s in result.stages:
            assert s.status == StageStatus.NOT_STARTED

    def test_duplicate_project_number_rejected(self, db: ProjectDB) -> None:
        db.insert_project(_new_project())
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_project(_new_project())

    def test_insert_preserves_original_record(self, db: ProjectDB) -> None:
        p = _new_project(original_record_done=True)
        result = db.insert_project(p)
        assert result.original_record_done is True


# ────────────────────────────────────────────────────────────────
class TestGetProject:
    def test_get_existing(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        fetched = db.get_project(inserted.project_id)
        assert fetched.project_id == inserted.project_id
        assert fetched.name == inserted.name
        assert len(fetched.stages) == 7

    def test_get_not_found_raises(self, db: ProjectDB) -> None:
        with pytest.raises(ProjectNotFoundError):
            db.get_project(999)

    def test_stage_names_match_builtin_order(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        fetched = db.get_project(inserted.project_id)
        stage_names = [s.name for s in fetched.stages]
        assert stage_names == list(BUILTIN_STAGE_NAMES)


# ────────────────────────────────────────────────────────────────
class TestListProjects:
    def test_empty_returns_empty_list(self, db: ProjectDB) -> None:
        assert db.list_projects() == []

    def test_returns_inserted_projects_order_by_created_desc(self, db: ProjectDB) -> None:
        db.insert_project(_new_project(project_number="P001"))
        p2 = db.insert_project(_new_project(project_number="P002"))
        projects = db.list_projects()
        assert len(projects) == 2
        # 后创建的排前面
        assert projects[0].project_id == p2.project_id


# ────────────────────────────────────────────────────────────────
class TestUpdateProject:
    def test_update_basic_fields(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        updated = Project(
            project_id=inserted.project_id,
            project_number=inserted.project_number,
            name="新名称",
            client="新委托方",
            inspection_type="新类型",
            amount=999.0,
            notes="新备注",
            original_record_done=True,
            stages=inserted.stages,
            folder_path=inserted.folder_path,
            created_at=inserted.created_at,
            updated_at=inserted.updated_at,
        )
        result = db.update_project(updated)
        assert result.name == "新名称"
        assert result.client == "新委托方"
        assert result.amount == 999.0
        assert result.original_record_done is True

    def test_update_does_not_touch_stages(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        # 改一个 stage 状态再 update —— 但 update_project 不更新 stages 表
        modified_stages = list(inserted.stages)
        modified_stages[0] = ProjectStage(
            name=modified_stages[0].name,
            status=StageStatus.COMPLETED,
        )
        updated = Project(
            project_id=inserted.project_id,
            project_number=inserted.project_number,
            name=inserted.name,
            client=inserted.client,
            inspection_type=inserted.inspection_type,
            stages=tuple(modified_stages),
            created_at=inserted.created_at,
            updated_at=inserted.updated_at,
        )
        db.update_project(updated)
        # 重新取出来 —— 阶段应该没变（因为 update_project 不写 stages）
        fetched = db.get_project(inserted.project_id)
        assert fetched.stages[0].status == StageStatus.NOT_STARTED


# ────────────────────────────────────────────────────────────────
class TestUpdateStage:
    def test_update_single_stage(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        result = db.update_stage(inserted.project_id, "现场检测", StageStatus.COMPLETED, note="已完成")
        assert result.stages[0].status == StageStatus.COMPLETED
        assert result.stages[0].note == "已完成"
        assert result.stages[0].updated_at is not None

    def test_update_stage_in_progress(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        result = db.update_stage(inserted.project_id, "报告编写", StageStatus.IN_PROGRESS)
        assert result.stages[2].status == StageStatus.IN_PROGRESS

    def test_update_stage_project_not_found(self, db: ProjectDB) -> None:
        with pytest.raises(ProjectNotFoundError):
            db.update_stage(999, "现场检测", StageStatus.COMPLETED)

    def test_update_stage_wrong_name(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        with pytest.raises(ProjectNotFoundError, match="阶段名称"):
            db.update_stage(inserted.project_id, "第一阶段", StageStatus.COMPLETED)


# ────────────────────────────────────────────────────────────────
class TestDeleteProject:
    def test_delete_removes_project_and_stages(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        assert db.delete_project(inserted.project_id) is True
        with pytest.raises(ProjectNotFoundError):
            db.get_project(inserted.project_id)
        # 确认 stages 也被级联删除
        cur = db.conn.execute(
            "SELECT COUNT(*) FROM project_stages WHERE project_id=?",
            (inserted.project_id,),
        )
        assert cur.fetchone()[0] == 0

    def test_delete_nonexistent(self, db: ProjectDB) -> None:
        assert db.delete_project(999) is False


# ────────────────────────────────────────────────────────────────
class TestArchiveProject:
    def test_archive_marks_all_completed(self, db: ProjectDB) -> None:
        inserted = db.insert_project(_new_project())
        result = db.archive_project(inserted.project_id)
        assert result.is_all_completed is True
        for s in result.stages:
            assert s.status == StageStatus.COMPLETED

    def test_archive_not_found(self, db: ProjectDB) -> None:
        with pytest.raises(ProjectNotFoundError):
            db.archive_project(999)
