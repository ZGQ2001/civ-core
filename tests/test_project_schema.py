"""项目管理看板 — 领域模型测试。

测试覆盖：
  StageStatus 枚举（三个状态值）
  ProjectStage dataclass：构造、默认值、校验
  Project dataclass：最小构造、必填校验、金额校验、阶段数校验、
                      frozen 不可变性、日期自动填充
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from civ_core.domain.project_schema import Project, ProjectStage, StageStatus


# ── helpers ──────────────────────────────────────────────────────
def _stage(name: str = "现场检测", status: StageStatus = StageStatus.NOT_STARTED) -> ProjectStage:
    """造一个最小合法 ProjectStage。"""
    return ProjectStage(name=name, status=status)


def _seven_stages() -> list[ProjectStage]:
    """7 个预设阶段，全部 NOT_STARTED。"""
    names = [
        "现场检测", "数据处理", "报告编写", "提交审核",
        "审核通过", "交给甲方", "归档",
    ]
    return [ProjectStage(name=n, status=StageStatus.NOT_STARTED) for n in names]


def _project(**override: object) -> Project:
    """造一个最小合法 Project（7 阶段 + 默认值）。"""
    kwargs: dict[str, object] = {
        "project_number": "P2024001",
        "name": "小米智能制造产业基地施工质量评价",
        "client": "小米集团",
        "inspection_type": "施工质量评价",
        "amount": 186000.0,
        "stages": tuple(_seven_stages()),
    }
    kwargs.update(override)
    return Project(**kwargs)  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────
# StageStatus 枚举
# ────────────────────────────────────────────────────────────────
class TestStageStatus:
    def test_values(self) -> None:
        assert StageStatus.NOT_STARTED.value == "not_started"
        assert StageStatus.IN_PROGRESS.value == "in_progress"
        assert StageStatus.COMPLETED.value == "completed"

    def test_from_str_roundtrip(self) -> None:
        for v in ("not_started", "in_progress", "completed"):
            assert StageStatus(v) is not None


# ────────────────────────────────────────────────────────────────
# ProjectStage
# ────────────────────────────────────────────────────────────────
class TestProjectStage:
    def test_construct_minimal(self) -> None:
        s = ProjectStage(name="现场检测", status=StageStatus.NOT_STARTED)
        assert s.name == "现场检测"
        assert s.status == StageStatus.NOT_STARTED

    def test_default_note_empty(self) -> None:
        s = _stage()
        assert s.note == ""

    def test_default_updated_at_none(self) -> None:
        s = _stage()
        assert s.updated_at is None

    def test_with_updated_at(self) -> None:
        now = datetime(2026, 5, 15, 14, 30)
        s = ProjectStage(name="报告编写", status=StageStatus.IN_PROGRESS, updated_at=now, note="初稿")
        assert s.updated_at == now
        assert s.note == "初稿"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            ProjectStage(name="", status=StageStatus.NOT_STARTED)

    def test_whitespace_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            ProjectStage(name="   ", status=StageStatus.NOT_STARTED)

    def test_frozen_mutate_rejected(self) -> None:
        s = _stage()
        with pytest.raises(FrozenInstanceError):
            s.name = "其他"  # type: ignore[misc]


# ────────────────────────────────────────────────────────────────
# Project
# ────────────────────────────────────────────────────────────────
class TestProjectMinimal:
    """最小合法构造。"""

    def test_all_fields_set(self) -> None:
        p = _project()
        assert p.project_number == "P2024001"
        assert p.name == "小米智能制造产业基地施工质量评价"
        assert p.client == "小米集团"
        assert p.inspection_type == "施工质量评价"
        assert p.amount == 186000.0
        assert p.folder_path is None
        assert p.original_record_done is False
        assert len(p.stages) == 7
        assert p.notes == ""

    def test_created_at_auto_filled(self) -> None:
        p = _project()
        assert isinstance(p.created_at, datetime)

    def test_updated_at_auto_filled(self) -> None:
        p = _project()
        assert isinstance(p.updated_at, datetime)

    def test_created_equals_updated_on_new(self) -> None:
        p = _project()
        assert p.created_at == p.updated_at


class TestProjectValidation:
    def test_empty_project_number_rejected(self) -> None:
        with pytest.raises(ValueError, match="project_number"):
            _project(project_number="")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            _project(name="   ")

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="amount"):
            _project(amount=-100.0)

    def test_zero_amount_accepted(self) -> None:
        p = _project(amount=0.0)
        assert p.amount == 0.0

    def test_wrong_stage_count_rejected(self) -> None:
        # 6 个阶段 → 拒绝
        with pytest.raises(ValueError, match="7"):
            _project(stages=tuple(_seven_stages()[:6]))

        # 8 个阶段 → 拒绝
        eight = _seven_stages() + [_stage(name="多余的")]
        with pytest.raises(ValueError, match="7"):
            _project(stages=tuple(eight))


class TestProjectDefaultValues:
    def test_folder_path_default_none(self) -> None:
        p = _project()
        assert p.folder_path is None

    def test_original_record_done_default_false(self) -> None:
        p = _project()
        assert p.original_record_done is False

    def test_notes_default_empty(self) -> None:
        p = _project()
        assert p.notes == ""


class TestProjectFrozen:
    def test_mutate_rejected(self) -> None:
        p = _project()
        with pytest.raises(FrozenInstanceError):
            p.name = "换个名字"  # type: ignore[misc]

    def test_mutate_stage_rejected(self) -> None:
        p = _project()
        with pytest.raises(FrozenInstanceError):
            p.stages = ()  # type: ignore[misc]


class TestProjectEquality:
    """值对象语义：同字段 == True。"""

    def test_same_fields_equal(self) -> None:
        now = datetime(2026, 5, 15, 12, 0, 0)
        p1 = _project(created_at=now, updated_at=now)
        p2 = _project(created_at=now, updated_at=now)
        assert p1 == p2

    def test_different_fields_not_equal(self) -> None:
        p1 = _project()
        p2 = _project(name="另一个项目")
        assert p1 != p2


class TestProjectHelperProperties:
    """便利属性：计算属性不走 DB，纯基于 stages。"""

    def test_completed_count_zero_on_new(self) -> None:
        p = _project()
        assert p.completed_stage_count == 0

    def test_completed_count(self) -> None:
        stages = [
            _stage("现场检测", StageStatus.COMPLETED),
            _stage("数据处理", StageStatus.IN_PROGRESS),
            _stage("报告编写", StageStatus.COMPLETED),
            _stage("提交审核", StageStatus.NOT_STARTED),
            _stage("审核通过", StageStatus.NOT_STARTED),
            _stage("交给甲方", StageStatus.COMPLETED),
            _stage("归档", StageStatus.NOT_STARTED),
        ]
        p = _project(stages=tuple(stages))
        assert p.completed_stage_count == 3

    def test_is_all_completed(self) -> None:
        all_done = [
            _stage(n, StageStatus.COMPLETED)
            for n in ["现场检测", "数据处理", "报告编写", "提交审核", "审核通过", "交给甲方", "归档"]
        ]
        p = _project(stages=tuple(all_done))
        assert p.is_all_completed is True

    def test_is_all_completed_false(self) -> None:
        p = _project()
        assert p.is_all_completed is False

    def test_in_progress_count(self) -> None:
        stages = [
            _stage("现场检测", StageStatus.IN_PROGRESS),
            _stage("数据处理", StageStatus.IN_PROGRESS),
            _stage("报告编写", StageStatus.NOT_STARTED),
            _stage("提交审核", StageStatus.NOT_STARTED),
            _stage("审核通过", StageStatus.NOT_STARTED),
            _stage("交给甲方", StageStatus.IN_PROGRESS),
            _stage("归档", StageStatus.NOT_STARTED),
        ]
        p = _project(stages=tuple(stages))
        assert p.in_progress_count == 3


class TestProjectColumnOrder:
    """Board 看板分列所需的状态判断。"""

    def test_pending_when_all_not_started(self) -> None:
        p = _project()
        assert p.board_column() == "待处理"

    def test_in_progress_when_mixed(self) -> None:
        stages = [
            _stage("现场检测", StageStatus.COMPLETED),
            _stage("数据处理", StageStatus.COMPLETED),
            _stage("报告编写", StageStatus.NOT_STARTED),
            _stage("提交审核", StageStatus.NOT_STARTED),
            _stage("审核通过", StageStatus.NOT_STARTED),
            _stage("交给甲方", StageStatus.NOT_STARTED),
            _stage("归档", StageStatus.NOT_STARTED),
        ]
        p = _project(stages=tuple(stages))
        # 有已完成但未全部完成 → 进行中
        assert p.board_column() == "进行中"

    def test_completed_when_all_completed(self) -> None:
        all_done = [_stage(n, StageStatus.COMPLETED) for n in [
            "现场检测", "数据处理", "报告编写", "提交审核", "审核通过", "交给甲方", "归档",
        ]]
        p = _project(stages=tuple(all_done))
        assert p.board_column() == "已完成"
