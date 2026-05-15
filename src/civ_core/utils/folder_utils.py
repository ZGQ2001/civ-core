"""文件夹工具：Shell 调用集中点。

按 CLAUDE.md 总纲：所有 subprocess / COM 调用集中在 utils/ 下。
本模块负责 `open_folder`（调用 Windows explorer 打开文件夹）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ── 异常 ─────────────────────────────────────────────────────────
class FolderCreationError(RuntimeError):
    """文件夹创建失败时抛出。"""


# ── 核心函数 ─────────────────────────────────────────────────────
def open_folder(path: Path) -> None:
    """用 Windows 资源管理器打开文件夹。

    前置条件：path 必须存在且为目录。
    Raises: FileNotFoundError 如果路径不存在。
    """
    if not path.exists():
        raise FileNotFoundError(f"文件夹不存在: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"路径不是文件夹: {path}")

    subprocess.run(
        ["explorer", str(path)],
        check=False,
    )
    log.info("已打开文件夹: %s", path)
