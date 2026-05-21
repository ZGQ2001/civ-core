"""files handlers：文件树列举 + 文件元信息（前端 Explorer 用）。

RPC 方法：
  files.list_dir(path, show_hidden=False) -> {entries: [...]}
  files.exists(path) -> {exists: bool, is_dir: bool, is_file: bool}

单条 entry：
  {name: str, path: str, is_dir: bool, size: int | None, mtime: float | None}

默认隐藏 .civ-core 和点开头文件（VSCode Explorer 默认行为）。
"""

from __future__ import annotations

from pathlib import Path

# RPC 暴露白名单（防 Path 被 register_module 误注册）
__all__ = ["list_dir", "exists"]

# 总是隐藏的应用专属目录（用户 show_hidden=True 也不显示，避免污染业务视图）
_ALWAYS_HIDDEN = {".civ-core"}


def list_dir(path: str, show_hidden: bool = False) -> dict:
    """列举目录下一级内容。子目录排前，按名字升序。"""
    p = Path(path)
    if not p.is_dir():
        raise ValueError(f"不是目录：{path}")
    entries: list[dict] = []
    for child in p.iterdir():
        name = child.name
        if name in _ALWAYS_HIDDEN:
            continue
        if not show_hidden and name.startswith("."):
            continue
        try:
            st = child.stat()
            size = st.st_size if child.is_file() else None
            mtime: float | None = st.st_mtime
        except OSError:
            size = None
            mtime = None
        entries.append(
            {
                "name": name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": size,
                "mtime": mtime,
            }
        )
    # 目录在前 + 字母序
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return {"entries": entries}


def exists(path: str) -> dict:
    p = Path(path)
    return {
        "exists": p.exists(),
        "is_dir": p.is_dir(),
        "is_file": p.is_file(),
    }
