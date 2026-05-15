"""项目文件夹操作：创建项目目录结构 + 打开文件夹。

按 CLAUDE.md 分层：infra_io 层负责 IO 操作（文件夹创建），
Shell 调用（explorer）委托给 utils/folder_utils.py。

文件夹命名格式：日期-编号-项目名（如 20260515-P2024001-小米基地检测）
子文件夹：委托方提供资料 / 图纸 / 报告 / 数据
"""

from __future__ import annotations

from pathlib import Path

from civ_core.utils.folder_utils import open_folder as _open_folder
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 内置子文件夹（4 个，不可变） ──────────────────────────────────
SUBFOLDER_NAMES: tuple[str, str, str, str] = (
    "委托方提供资料",
    "图纸",
    "报告",
    "数据",
)


# ── 文件夹命名 ──────────────────────────────────────────────────
def generate_folder_name(date_str: str, project_number: str, name: str) -> str:
    """生成项目文件夹名：日期-编号-项目名。

    date_str 必须是 8 位数字字符串（如 "20260515"）。
    project_number 和 name 不可为空。

    Raises: ValueError 如果参数不合法。
    """
    if len(date_str) != 8 or not date_str.isdigit():
        raise ValueError(f"日期必须是 8 位数字（如 20260515），得到 {date_str!r}")
    if not project_number or not project_number.strip():
        raise ValueError(f"项目编号不可为空，得到 {project_number!r}")
    if not name or not name.strip():
        raise ValueError(f"项目名称不可为空，得到 {name!r}")

    return f"{date_str}-{project_number}-{name}"


# ── 创建项目文件夹 ──────────────────────────────────────────────
def create_project_folder(
    parent_dir: Path,
    date_str: str,
    project_number: str,
    name: str,
) -> Path:
    """在 parent_dir 下创建项目文件夹及 4 个子文件夹。

    幂等：如果项目文件夹已存在，只补建缺失的子文件夹。
    父目录不存在时自动创建。

    返回：项目文件夹的 Path。
    """
    folder_name = generate_folder_name(date_str, project_number, name)
    project_dir = parent_dir / folder_name

    # 创建项目文件夹（exist_ok=True 实现幂等）
    project_dir.mkdir(parents=True, exist_ok=True)
    log.info("项目文件夹已就绪: %s", project_dir)

    # 补建缺失的子文件夹
    for sub in SUBFOLDER_NAMES:
        sub_path = project_dir / sub
        if not sub_path.exists():
            sub_path.mkdir(parents=True, exist_ok=True)
            log.debug("  子文件夹已创建: %s", sub_path)

    return project_dir


# ── 打开项目文件夹 ──────────────────────────────────────────────
def open_project_folder(path: Path | None) -> bool | None:
    """打开项目文件夹（委托给 utils/folder_utils.open_folder）。

    path 为 None 时返回 None（项目未绑定文件夹）。
    返回 True 表示成功打开。

    Raises: FileNotFoundError 如果路径不存在。
    """
    if path is None:
        return None
    _open_folder(path)
    return True


# ── 重新导出 open_folder（方便统一引用） ─────────────────────────
open_folder = _open_folder
