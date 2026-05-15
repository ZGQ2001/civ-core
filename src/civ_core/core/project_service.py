"""project_service：项目管理业务逻辑层。

按 CLAUDE.md 分层：
  • 入参/出参全部是 domain dataclass（Project / ProjectStage / StageStatus）
  • 禁止直接读写文件；IO 通过 infra_io 层（ProjectDB + project_folder）
  • 统一异常包装：infra_io 抛出的 ProjectNotFoundError → ValueError
"""

from __future__ import annotations

from pathlib import Path

from civ_core.domain.project_schema import (
    Project,
    StageStatus,
)
from civ_core.infra_io.project_db import ProjectDB, ProjectNotFoundError
from civ_core.infra_io.project_folder import create_project_folder
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


class ProjectService:

    def __init__(self, db: ProjectDB) -> None:
        self._db = db

    def create_project(
        self,
        project: Project,
        *,
        create_folder: bool = True,
        folder_parent: Path | None = None,
        date_str: str | None = None,
    ) -> Project:
        try:
            inserted = self._db.insert_project(project)
        except Exception as e:
            if "UNIQUE" in str(e) or "unique" in str(e).lower():
                raise ValueError(f"项目编号 {project.project_number!r} 重复") from e
            raise

        if create_folder:
            if folder_parent is None or date_str is None:
                log.info("create_folder=True 但未提供 folder_parent/date_str，跳过文件夹创建")
            else:
                try:
                    folder_path = create_project_folder(
                        folder_parent, date_str,
                        project.project_number, project.name,
                    )
                    updated = Project(
                        project_id=inserted.project_id,
                        project_number=inserted.project_number,
                        name=inserted.name,
                        client=inserted.client,
                        inspection_type=inserted.inspection_type,
                        amount=inserted.amount,
                        folder_path=folder_path,
                        original_record_done=inserted.original_record_done,
                        notes=inserted.notes,
                        stages=inserted.stages,
                        created_at=inserted.created_at,
                        updated_at=inserted.updated_at,
                    )
                    return self._db.update_project(updated)
                except Exception as e:
                    log.warning("文件夹创建失败（DB 记录已保留）: %s", e)

        return inserted

    def get_project(self, project_id: int) -> Project:
        try:
            return self._db.get_project(project_id)
        except ProjectNotFoundError as e:
            raise ValueError(f"项目 id={project_id} 不存在") from e

    def list_projects(self) -> list[Project]:
        return self._db.list_projects()

    def filter_projects(self, filter_type: str) -> list[Project]:
        all_projects = self._db.list_projects()
        if filter_type == "团队积压":
            return [
                p for p in all_projects
                if p.completed_stage_count == 0 and p.in_progress_count == 0
            ]
        elif filter_type == "正在进行":
            return [
                p for p in all_projects
                if not p.is_all_completed and (p.completed_stage_count > 0 or p.in_progress_count > 0)
            ]
        else:
            return [p for p in all_projects if not p.is_all_completed]

    def update_project(self, project: Project) -> Project:
        try:
            return self._db.update_project(project)
        except ProjectNotFoundError as e:
            raise ValueError(str(e)) from e

    def update_stage(
        self, project_id: int, stage_name: str, status: StageStatus, *, note: str = ""
    ) -> Project:
        try:
            return self._db.update_stage(project_id, stage_name, status, note=note)
        except ProjectNotFoundError as e:
            raise ValueError(str(e)) from e

    def delete_project(self, project_id: int) -> bool:
        return self._db.delete_project(project_id)

    def archive_project(self, project_id: int) -> Project:
        try:
            return self._db.archive_project(project_id)
        except ProjectNotFoundError as e:
            raise ValueError(str(e)) from e

    def get_statistics(self) -> dict[str, object]:
        all_projects = self._db.list_projects()
        active = [p for p in all_projects if not p.is_all_completed]
        return {"total": len(active), "total_amount": sum(p.amount for p in active)}
