"""project_db：项目管理 SQLite 持久化层。

职责：
  • 建表（幂等）
  • CRUD：insert / get / list / update / delete
  • update_stage：更新单阶段状态 + note + updated_at
  • archive_project：全阶段标记 COMPLETED

设计要点：
  • 直接接收/返回 domain/project_schema 的 Project dataclass
  • SQLite 存时间用 ISO 8601 字符串；读写时 ↔ datetime 互转
  • stages 存在独立表 project_stages（每个项目 7 行），用 JOIN 重建
  • project_number 有 UNIQUE 约束
  • 级联删除：delete_project 同步清理 stages 表
  • 不管理连接生命周期（由外部传入 conn）；DB 文件路径由调用方决定
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from civ_core.domain.project_schema import (
    BUILTIN_STAGE_NAMES,
    Project,
    ProjectStage,
    StageStatus,
)
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 异常 ─────────────────────────────────────────────────────────
class ProjectNotFoundError(RuntimeError):
    """项目不存在时抛出（get / update / delete）。"""


# ── SQL 语句常量 ────────────────────────────────────────────────
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number    TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    client            TEXT NOT NULL DEFAULT '',
    inspection_type   TEXT NOT NULL DEFAULT '',
    amount            REAL NOT NULL DEFAULT 0.0,
    folder_path       TEXT,
    original_record_done INTEGER NOT NULL DEFAULT 0,
    notes             TEXT NOT NULL DEFAULT '',
    is_on_hold        INTEGER NOT NULL DEFAULT 0,
    is_archived       INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_stages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stage_name  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'not_started',
    note        TEXT NOT NULL DEFAULT '',
    updated_at  TEXT,
    UNIQUE(project_id, stage_name)
);
"""

INSERT_PROJECT_SQL = """
INSERT INTO projects (project_number, name, client, inspection_type,
                       amount, folder_path, original_record_done,
                       notes, is_on_hold, is_archived,
                       created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_STAGE_SQL = """
INSERT INTO project_stages (project_id, stage_name, status, note, updated_at)
VALUES (?, ?, ?, ?, ?)
"""

SELECT_PROJECT_SQL = """
SELECT id, project_number, name, client, inspection_type,
       amount, folder_path, original_record_done, notes,
       is_on_hold, is_archived,
       created_at, updated_at
FROM projects WHERE id = ?
"""

SELECT_STAGES_SQL = """
SELECT stage_name, status, note, updated_at
FROM project_stages WHERE project_id = ? ORDER BY id
"""

LIST_ALL_SQL = """
SELECT id, project_number, name, client, inspection_type,
       amount, folder_path, original_record_done, notes,
       is_on_hold, is_archived,
       created_at, updated_at
FROM projects ORDER BY created_at DESC, id DESC
"""

UPDATE_PROJECT_SQL = """
UPDATE projects SET
    name = ?, client = ?, inspection_type = ?,
    amount = ?, folder_path = ?, original_record_done = ?,
    notes = ?, is_on_hold = ?, is_archived = ?, updated_at = ?
WHERE id = ?
"""

# 单独切换两个布尔状态，不动其他字段（避免 update_project 把别处的草稿覆盖掉）
UPDATE_ON_HOLD_SQL = """
UPDATE projects SET is_on_hold = ?, updated_at = ? WHERE id = ?
"""

UPDATE_ARCHIVED_SQL = """
UPDATE projects SET is_archived = ?, updated_at = ? WHERE id = ?
"""

UPDATE_STAGE_SQL = """
UPDATE project_stages SET status = ?, note = ?, updated_at = ?
WHERE project_id = ? AND stage_name = ?
"""

ARCHIVE_ALL_STAGES_SQL = """
UPDATE project_stages SET status = 'completed', note = '已归档', updated_at = ?
WHERE project_id = ?
"""

DELETE_STAGES_SQL = "DELETE FROM project_stages WHERE project_id = ?"
DELETE_PROJECT_SQL = "DELETE FROM projects WHERE id = ?"


# ── 工具函数 ────────────────────────────────────────────────────
def _dt_to_iso(dt: datetime | None) -> str | None:
    """datetime → ISO 8601 字符串（UTC）。"""
    if dt is None:
        return None
    return dt.isoformat()


def _iso_to_dt(s: str | None) -> datetime | None:
    """ISO 8601 字符串 → datetime；None 或空字符串 → None。"""
    if not s:
        return None
    return datetime.fromisoformat(s)


def _row_to_project(row: sqlite3.Row, stages: Sequence[ProjectStage]) -> Project:
    """将 projects 表一行 + 7 个 stage → Project dataclass。"""
    return Project(
        project_id=row["id"],
        project_number=row["project_number"],
        name=row["name"],
        client=row["client"],
        inspection_type=row["inspection_type"],
        amount=row["amount"],
        folder_path=Path(row["folder_path"]) if row["folder_path"] else None,
        original_record_done=bool(row["original_record_done"]),
        notes=row["notes"],
        is_on_hold=bool(row["is_on_hold"]),
        is_archived=bool(row["is_archived"]),
        stages=tuple(stages),
        created_at=_iso_to_dt(row["created_at"]) or datetime.now(timezone.utc),
        updated_at=_iso_to_dt(row["updated_at"]) or datetime.now(timezone.utc),
    )


def _stages_from_rows(rows: Sequence[sqlite3.Row]) -> list[ProjectStage]:
    """将 project_stages 查询结果 → ProjectStage 列表。"""
    return [
        ProjectStage(
            name=r["stage_name"],
            status=StageStatus(r["status"]),
            note=r["note"] or "",
            updated_at=_iso_to_dt(r["updated_at"]),
        )
        for r in rows
    ]


# ════════════════════════════════════════════════════════════════
# ProjectDB
# ════════════════════════════════════════════════════════════════
class ProjectDB:
    """项目管理 SQLite 持久化。

    用法：
        conn = sqlite3.connect("~/.civ-core/projects.db")
        conn.row_factory = sqlite3.Row
        db = ProjectDB(conn)
        db.create_tables()
        p = db.insert_project(...)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # 启用外键约束（确保 ON DELETE CASCADE 生效）
        conn.execute("PRAGMA foreign_keys = ON")

    # ── 建表 ────────────────────────────────────────────────────
    def create_tables(self) -> None:
        """幂等建表（IF NOT EXISTS）+ 老 DB 自动补列迁移。

        老版本 DB 没有 is_on_hold/is_archived，启动时用 PRAGMA table_info
        探查并 ALTER 补列。SQLite 不支持 ADD COLUMN IF NOT EXISTS。
        """
        with self.conn:
            self.conn.executescript(CREATE_TABLES_SQL)
            self._migrate_add_status_flags()

    def _migrate_add_status_flags(self) -> None:
        """补列：is_on_hold / is_archived（老 DB 升级路径）。"""
        cur = self.conn.execute("PRAGMA table_info(projects)")
        existing = {row[1] for row in cur.fetchall()}  # row[1] = name
        if "is_on_hold" not in existing:
            self.conn.execute(
                "ALTER TABLE projects ADD COLUMN is_on_hold INTEGER NOT NULL DEFAULT 0"
            )
            log.info("DB 迁移：projects 表补列 is_on_hold")
        if "is_archived" not in existing:
            self.conn.execute(
                "ALTER TABLE projects ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"
            )
            log.info("DB 迁移：projects 表补列 is_archived")

    # ── 插入 ────────────────────────────────────────────────────
    def insert_project(self, project: Project) -> Project:
        """插入新项目 + 7 条初始 stage 记录，返回带 project_id 的 Project。

        project_id 字段被忽略（DB 自增）。
        Raises: sqlite3.IntegrityError 如果 project_number 重复。
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        folder_path_str = str(project.folder_path) if project.folder_path else None

        with self.conn:
            cur = self.conn.execute(
                INSERT_PROJECT_SQL,
                (
                    project.project_number,
                    project.name,
                    project.client,
                    project.inspection_type,
                    project.amount,
                    folder_path_str,
                    1 if project.original_record_done else 0,
                    project.notes,
                    1 if project.is_on_hold else 0,
                    1 if project.is_archived else 0,
                    now_iso,
                    now_iso,
                ),
            )
            project_id = cur.lastrowid

            # 插入 7 条阶段记录（使用 Project 对象中的实际状态）
            for stage in project.stages:
                self.conn.execute(
                    INSERT_STAGE_SQL,
                    (project_id, stage.name, stage.status.value, stage.note, _dt_to_iso(stage.updated_at))
                )

        # 从 DB 重新读取以确保一致性
        return self.get_project(project_id)

    # ── 查询单条 ────────────────────────────────────────────────
    def get_project(self, project_id: int) -> Project:
        """按 project_id 查询单个项目（含 7 阶段）。

        Raises: ProjectNotFoundError。
        """
        project_row = self.conn.execute(SELECT_PROJECT_SQL, (project_id,)).fetchone()
        if project_row is None:
            raise ProjectNotFoundError(f"项目 id={project_id} 不存在")

        stage_rows = self.conn.execute(SELECT_STAGES_SQL, (project_id,)).fetchall()
        stages = _stages_from_rows(stage_rows)
        return _row_to_project(project_row, stages)

    # ── 全量列表 ────────────────────────────────────────────────
    def list_projects(self) -> list[Project]:
        """按创建时间倒序返回所有项目（含各自 7 阶段）。"""
        project_rows = self.conn.execute(LIST_ALL_SQL).fetchall()
        result: list[Project] = []
        for row in project_rows:
            stage_rows = self.conn.execute(
                SELECT_STAGES_SQL, (row["id"],)
            ).fetchall()
            stages = _stages_from_rows(stage_rows)
            result.append(_row_to_project(row, stages))
        return result

    # ── 更新项目字段 ────────────────────────────────────────────
    def update_project(self, project: Project) -> Project:
        """更新项目的业务字段（不更新 stages 表）。

        project_number 不会被更新（它是唯一标识符）。
        更新后重新从 DB 加载返回。
        """
        # 先确认存在
        self.get_project(project.project_id)

        now_iso = datetime.now(timezone.utc).isoformat()
        folder_path_str = str(project.folder_path) if project.folder_path else None

        with self.conn:
            self.conn.execute(
                UPDATE_PROJECT_SQL,
                (
                    project.name,
                    project.client,
                    project.inspection_type,
                    project.amount,
                    folder_path_str,
                    1 if project.original_record_done else 0,
                    project.notes,
                    1 if project.is_on_hold else 0,
                    1 if project.is_archived else 0,
                    now_iso,
                    project.project_id,
                ),
            )

        return self.get_project(project.project_id)

    # ── 状态标志切换 ─────────────────────────────────────────────
    def set_on_hold(self, project_id: int, value: bool) -> Project:
        """切换 is_on_hold 标志；不影响其他字段。"""
        self.get_project(project_id)  # 确认存在
        now_iso = _dt_to_iso(datetime.now(timezone.utc))
        with self.conn:
            self.conn.execute(UPDATE_ON_HOLD_SQL, (1 if value else 0, now_iso, project_id))
        return self.get_project(project_id)

    def set_archived(self, project_id: int, value: bool) -> Project:
        """切换 is_archived 标志；不影响其他字段。"""
        self.get_project(project_id)  # 确认存在
        now_iso = _dt_to_iso(datetime.now(timezone.utc))
        with self.conn:
            self.conn.execute(UPDATE_ARCHIVED_SQL, (1 if value else 0, now_iso, project_id))
        return self.get_project(project_id)

    # ── 更新单阶段 ──────────────────────────────────────────────
    def update_stage(
        self,
        project_id: int,
        stage_name: str,
        status: StageStatus,
        *,
        note: str = "",
    ) -> Project:
        """更新单个进度阶段的状态 + 备注 + 时间戳。

        若 stage_name 不属于 BUILTIN_STAGE_NAMES → ProjectNotFoundError。
        """
        if stage_name not in BUILTIN_STAGE_NAMES:
            raise ProjectNotFoundError(f"阶段名称 '{stage_name}' 不在内置 7 阶段中")

        # 确认项目存在
        self.get_project(project_id)

        now_iso = _dt_to_iso(datetime.now(timezone.utc))
        with self.conn:
            cur = self.conn.execute(
                UPDATE_STAGE_SQL,
                (status.value, note, now_iso, project_id, stage_name),
            )
            if cur.rowcount == 0:
                raise ProjectNotFoundError(
                    f"项目 id={project_id} 的阶段 '{stage_name}' 不存在"
                )

        return self.get_project(project_id)

    # ── 删除 ────────────────────────────────────────────────────
    def delete_project(self, project_id: int) -> bool:
        """硬删除项目及其全部阶段记录。

        ON DELETE CASCADE 自动清理 stages 表。
        返回 True 表示删除成功，False 表示项目不存在。
        """
        with self.conn:
            cur = self.conn.execute(DELETE_PROJECT_SQL, (project_id,))
            return cur.rowcount > 0

    # ── 归档 ────────────────────────────────────────────────────
    def archive_project(self, project_id: int) -> Project:
        """将所有 7 个阶段标记为 COMPLETED（软归档）。

        不删除项目，只是标记全部阶段已完成。
        """
        self.get_project(project_id)  # 确认存在

        now_iso = _dt_to_iso(datetime.now(timezone.utc))
        with self.conn:
            self.conn.execute(ARCHIVE_ALL_STAGES_SQL, (now_iso, project_id))

        return self.get_project(project_id)
