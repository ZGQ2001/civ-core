"""workspace handlers：当前工作区路径的读/写/新建标准结构。

RPC 方法（注册时前缀 "workspace."）：
  workspace.last() -> {path: str | null}
  workspace.set(path) -> {ok: bool, path: str}
  workspace.clear() -> {ok: true}
  workspace.create_standard(parent_dir, name) -> {ok: bool, path: str}

为什么走 ~/.civ-core/workspace.json 而非旧的 QSettings：
  - 新前端不是 Qt 应用，没法读 QSettings store
  - 简单的 JSON 文件跨进程读写更直接，调试可视
"""

from __future__ import annotations

import json
from pathlib import Path

from civ_core.infra_io.workspace_scaffold import create_standard_structure

# RPC 暴露的方法白名单：避免把顶部 import 的工具类（Path / create_standard_structure）
# 被 register_module 误注册成 RPC 方法
__all__ = ["last", "set", "clear", "create_standard"]

_STORE = Path("~/.civ-core/workspace.json").expanduser()


def _read_store() -> dict:
    if not _STORE.exists():
        return {}
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_store(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def last() -> dict:
    """返回上次打开的工作区路径；不存在/路径已失效 → path=None。"""
    data = _read_store()
    raw = data.get("last_workspace")
    if not raw:
        return {"path": None}
    p = Path(str(raw))
    if not p.is_dir():
        return {"path": None}
    return {"path": str(p)}


def set(path: str) -> dict:  # noqa: A001 (RPC 接口要求 method 名为 "set")
    """记下当前工作区路径。"""
    p = Path(path)
    if not p.is_dir():
        raise ValueError(f"工作区必须是已存在的目录：{path}")
    data = _read_store()
    data["last_workspace"] = str(p)
    _write_store(data)
    return {"ok": True, "path": str(p)}


def clear() -> dict:
    """清掉记忆（用户主动）。"""
    data = _read_store()
    data.pop("last_workspace", None)
    _write_store(data)
    return {"ok": True}


def create_standard(parent_dir: str, name: str) -> dict:
    """在 parent_dir 下创建 name 文件夹 + 标准骨架。

    幂等：已存在的子文件夹不会被破坏。
    """
    parent = Path(parent_dir)
    if not parent.is_dir():
        raise ValueError(f"父目录不存在：{parent_dir}")
    if not name or "/" in name or "\\" in name:
        raise ValueError(f"项目名不合法：{name!r}")
    root = parent / name.strip()
    create_standard_structure(root)
    return {"ok": True, "path": str(root)}
