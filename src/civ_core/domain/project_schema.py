"""项目管理看板 — 领域数据契约。

四个契约：
  StageStatus      — 阶段状态枚举（三态）
  ProjectStage     — 单个进度阶段（7 个组成项目进度）
  Project          — 项目主体（含所有字段 + 计算属性）
  BUILTIN_STAGES   — 内置 7 阶段名称（不可变元组）

设计原则（总纲）：
  • 纯 dataclass + __post_init__ 校验，零外部依赖
  • frozen=True（不可变值对象）—— 修改走 infra_io 层重新构建
  • 路径字段用 pathlib.Path
  • 计算属性（completed_stage_count 等）不走 DB，纯基于 stages 元组
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

# ── 内置阶段名称 ─────────────────────────────────────────────────
BUILTIN_STAGE_NAMES: tuple[str, ...] = (
    "现场检测",
    "数据处理",
    "报告编写",
    "提交审核",
    "审核通过",
    "交给甲方",
    "归档",
)


# ── 阶段状态枚举 ─────────────────────────────────────────────────
class StageStatus(str, Enum):
    """进度阶段的三态枚举。

    为什么继承 str：方便 SQLite 存/取文本值；UI 显示中文时走映射。

    三态：
      NOT_STARTED — 尚未开始（灰圆点 ○）
      IN_PROGRESS — 正在进行（蓝圆点 ●）
      COMPLETED   — 已完成（绿勾 ✅）
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ── 阶段 ─────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ProjectStage:
    """项目进度中的一个阶段。

    注意：frozen=True 保证阶段不可原地修改；变更状态只能通过 infra_io 层
    构建新的 Project 实例替换旧值。
    """

    name: str
    status: StageStatus = StageStatus.NOT_STARTED
    note: str = ""
    updated_at: datetime | None = None  # 阶段最后一次变更时间；None = 未动过

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError(f"ProjectStage.name 不可为空，得到 {self.name!r}")


# ── 项目 ─────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Project:
    """一个工程检测项目。

    注意：
      project_id：自增主键（DB 管理，新建时可为 0 占位）
      stages：必须是 7 个阶段的元组（顺序 = BUILTIN_STAGE_NAMES）
      created_at / updated_at：datetime 对象（__post_init__ 自动填充 UTC）
      folder_path：None 表示未绑定本地文件夹
    """

    # ── 业务字段（用户必填） ────────────────────────────────
    project_number: str
    name: str
    client: str
    inspection_type: str

    # ── 可选业务字段 ────────────────────────────────────────
    amount: float = 0.0
    folder_path: Path | None = None
    original_record_done: bool = False
    notes: str = ""

    # ── 状态标志位（看板 4 档筛选用） ────────────────────────
    # 设计：is_on_hold / is_archived 完全独立，与 7 阶段进度互不关联。
    # 用户手动点「暂存」/「归档」才会切换；7 阶段全完成 ≠ 自动归档。
    is_on_hold: bool = False
    is_archived: bool = False

    # ── 进度 ────────────────────────────────────────────────
    stages: tuple[ProjectStage, ...] = field(default_factory=tuple)

    # ── 审计字段 ────────────────────────────────────────────
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── DB 主键（新建时为 0） ──────────────────────────────
    project_id: int = 0

    def __post_init__(self) -> None:
        # ─ 必填校验 ─
        if not self.project_number or not self.project_number.strip():
            raise ValueError(f"Project.project_number 不可为空，得到 {self.project_number!r}")
        if not self.name or not self.name.strip():
            raise ValueError(f"Project.name 不可为空，得到 {self.name!r}")
        if self.amount < 0:
            raise ValueError(f"Project.amount 必须 >= 0，得到 {self.amount}")

        # ─ 阶段数固定为 7 ─
        if len(self.stages) != 7:
            raise ValueError(
                f"Project.stages 必须恰好 7 个阶段，得到 {len(self.stages)} 个"
            )

        # ─ 路径自动转换 ─
        if self.folder_path is not None and not isinstance(self.folder_path, Path):
            object.__setattr__(self, "folder_path", Path(self.folder_path))

    # ══════════════════════════════════════════════════════════
    # 计算属性（不走 DB，纯基于 stages 元组）
    # ══════════════════════════════════════════════════════════

    @property
    def completed_stage_count(self) -> int:
        """已完成的阶段数（0–7）。"""
        return sum(1 for s in self.stages if s.status == StageStatus.COMPLETED)

    @property
    def in_progress_count(self) -> int:
        """进行中的阶段数（0–7）。"""
        return sum(1 for s in self.stages if s.status == StageStatus.IN_PROGRESS)

    @property
    def is_all_completed(self) -> bool:
        """全部 7 阶段是否都已完成。"""
        return self.completed_stage_count == 7

    def board_column(self) -> str:
        """看板 3 列归属判断。

        返回：
          "待处理"  — 全部 7 阶段 NOT_STARTED
          "进行中"  — 至少 1 个非 NOT_STARTED，且未全部完成
          "已完成"  — 全部 7 阶段 COMPLETED
        """
        if self.is_all_completed:
            return "已完成"
        if self.completed_stage_count == 0 and self.in_progress_count == 0:
            return "待处理"
        return "进行中"
