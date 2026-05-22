"""files handlers：文件树列举 + 文件元信息 + 增删改 + 复制移动 + 在系统打开。

RPC 方法：
  files.list_dir(path, show_hidden=False) -> {entries: [...]}
  files.exists(path) -> {exists: bool, is_dir: bool, is_file: bool}
  files.create_file(parent, name) -> {path}      在 parent 下创建空文件 name
  files.create_folder(parent, name) -> {path}    在 parent 下创建文件夹 name
  files.rename(path, new_name) -> {path}         同目录改名
  files.delete(path) -> {ok}                     发送到回收站（send2trash）
  files.copy(src, dst_parent) -> {path}          复制到 dst_parent 下，自动改名避免覆盖
  files.move(src, dst_parent) -> {path}          移动到 dst_parent 下
  files.reveal(path) -> {ok}                     在 Windows 资源管理器中定位选中此项

单条 entry：
  {name: str, path: str, is_dir: bool, size: int | None, mtime: float | None}

默认隐藏 .civ-core 和点开头文件（VSCode Explorer 默认行为）。

设计要点：
  - 不允许跨目录 rename（只是改名）；跨目录用 move
  - copy/move 的目标若同名 → 追加 "(2)" / "(3)" 后缀，与 Windows 资源管理器行为一致
  - delete 走 send2trash（已加依赖），失败会抛 RPC error 让前端弹错
  - reveal 用 explorer.exe /select,"path"；非 Windows 不支持
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from send2trash import send2trash

# RPC 暴露白名单
__all__ = [
    "list_dir",
    "exists",
    "create_file",
    "create_folder",
    "rename",
    "delete",
    "copy",
    "move",
    "reveal",
    "undo_delete",
]

# 总是隐藏的应用专属目录（用户 show_hidden=True 也不显示，避免污染业务视图）
_ALWAYS_HIDDEN = {".civ-core"}

# 非法字符（Windows 文件名）
_FORBIDDEN_NAME_CHARS = set('<>:"/\\|?*')
_FORBIDDEN_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _check_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("名称不能为空")
    if name != name.strip():
        raise ValueError("名称首尾不能含空格")
    if any(c in _FORBIDDEN_NAME_CHARS for c in name):
        raise ValueError(f'名称含非法字符 <>:"/\\|?*：{name!r}')
    stem = name.rsplit(".", 1)[0].upper()
    if stem in _FORBIDDEN_NAMES:
        raise ValueError(f"Windows 保留名：{name!r}")


def _unique_dst(parent: Path, name: str) -> Path:
    """返回 parent 下不冲突的目标路径；同名则追加 (2)/(3)/...

    保留扩展名：foo.xlsx 冲突 → foo (2).xlsx
    """
    candidate = parent / name
    if not candidate.exists():
        return candidate
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    else:
        ext = f".{ext}"
    for i in range(2, 1000):
        candidate = parent / f"{stem} ({i}){ext}"
        if not candidate.exists():
            return candidate
    raise OSError(f"无法生成不冲突的名字（已尝试 1000 次）：{parent / name}")


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


def create_file(parent: str, name: str) -> dict:
    """在 parent 下创建空文件 name；若同名存在则报错（前端会要求改名）。"""
    _check_name(name)
    pp = Path(parent)
    if not pp.is_dir():
        raise ValueError(f"父目录不存在：{parent}")
    target = pp / name
    if target.exists():
        raise FileExistsError(f"已存在：{target}")
    target.touch()
    return {"path": str(target)}


def create_folder(parent: str, name: str) -> dict:
    """在 parent 下创建文件夹 name；若同名存在则报错。"""
    _check_name(name)
    pp = Path(parent)
    if not pp.is_dir():
        raise ValueError(f"父目录不存在：{parent}")
    target = pp / name
    if target.exists():
        raise FileExistsError(f"已存在：{target}")
    target.mkdir()
    return {"path": str(target)}


def rename(path: str, new_name: str) -> dict:
    """同目录内改名；不允许跨目录。"""
    _check_name(new_name)
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"不存在：{path}")
    dst = src.parent / new_name
    if dst == src:
        return {"path": str(src)}
    if dst.exists():
        raise FileExistsError(f"已存在：{dst}")
    src.rename(dst)
    return {"path": str(dst)}


import time

import win32com.client

_undo_stack: list[dict] = []


def delete(path: str) -> dict:
    """直接发送到回收站，并记录原始路径以支持 5 分钟内撤销。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"不存在：{path}")

    send2trash(str(p))

    _undo_stack.append({"original_path": str(p), "name": p.name, "timestamp": time.time()})
    return {"ok": True}


def undo_delete() -> dict:
    """从回收站捞回最近一次删除的文件（仅限 5 分钟内）。"""
    if not _undo_stack:
        raise ValueError("没有可撤销的删除操作")

    item = _undo_stack.pop()
    if time.time() - item.get("timestamp", 0) > 300:
        _undo_stack.clear()
        raise ValueError("超过 5 分钟的删除不支持在 App 内撤销，请前往系统回收站手动还原。")

    orig = Path(item["original_path"])
    orig_name = item["name"]
    orig_dir = str(orig.parent)

    if orig.exists():
        # 如果原位置被占用，撤销失败，把记录塞回去
        _undo_stack.append(item)
        raise FileExistsError(f"无法还原：目标位置已有同名文件 {orig_name}")

    shell = win32com.client.Dispatch("Shell.Application")
    rb = shell.NameSpace(10)

    restored = False
    # 因为可能存在同名文件，需要倒序遍历以找到最近删除的匹配项
    for i in range(rb.Items().Count - 1, -1, -1):
        rb_item = rb.Items().Item(i)
        if rb_item.Name == orig_name:
            clean_dir = rb.GetDetailsOf(rb_item, 1).replace("\u200e", "").replace("\u200f", "")
            if clean_dir == orig_dir:
                try:
                    rb_item.InvokeVerb("undelete")
                    restored = True
                    break
                except Exception:
                    # 备用方案：通过动词名称匹配
                    for verb in rb_item.Verbs():
                        if "还原" in verb.Name or "Restore" in verb.Name:
                            verb.DoIt()
                            restored = True
                            break
                if restored:
                    break

    if not restored:
        raise FileNotFoundError("在回收站中未找到匹配的文件，可能已被彻底删除。")

    return {"restored_path": str(orig), "parent": str(orig.parent)}


def copy(src: str, dst_parent: str) -> dict:
    """复制到 dst_parent 下；同名自动追加 (2)/(3)。文件夹递归复制。"""
    s = Path(src)
    if not s.exists():
        raise FileNotFoundError(f"源不存在：{src}")
    dp = Path(dst_parent)
    if not dp.is_dir():
        raise ValueError(f"目标目录不存在：{dst_parent}")
    target = _unique_dst(dp, s.name)
    if s.is_dir():
        shutil.copytree(s, target)
    else:
        shutil.copy2(s, target)
    return {"path": str(target)}


def move(src: str, dst_parent: str) -> dict:
    """移动到 dst_parent 下；同名自动追加 (2)/(3)。"""
    s = Path(src)
    if not s.exists():
        raise FileNotFoundError(f"源不存在：{src}")
    dp = Path(dst_parent)
    if not dp.is_dir():
        raise ValueError(f"目标目录不存在：{dst_parent}")
    # 已在该目录下 → no-op
    if s.parent.resolve() == dp.resolve():
        return {"path": str(s)}
    target = _unique_dst(dp, s.name)
    shutil.move(str(s), str(target))
    return {"path": str(target)}


def reveal(path: str) -> dict:
    """在系统文件管理器中定位并选中此项（Windows: explorer /select）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"不存在：{path}")
    if sys.platform == "win32":
        # explorer.exe /select,"absolute path" — 注意 /select, 后无空格
        subprocess.Popen(  # noqa: S603 — explorer 是受信任的系统程序
            ["explorer.exe", f"/select,{os.path.normpath(str(p))}"],
            close_fds=True,
        )
    else:
        raise NotImplementedError("reveal 当前仅支持 Windows")
    return {"ok": True}
