"""文件 I/O、外部进程调用、stdout 行缓冲修复等系统层工具。

工程规范落地：
  ✓ logger（不再 print）
  ✓ subprocess 用 with 管理（CompletedProcess 自动清理）
  ✓ 异常带上下文，禁止 except: pass
  ✓ 文件对话框已剥离到 io/file_dialogs.py（避免 PySide6 与命令行业务混耦合）
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# stdout / I/O
# ──────────────────────────────────────────────────────────────────
def enable_line_buffered_stdout() -> None:
    """让 print 实时刷新，避免 IDE / 重定向场景下日志被块缓冲攒到最后。"""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if not callable(reconfigure):
        log.debug("sys.stdout 不支持 reconfigure（Python <3.7?），跳过")
        return
    try:
        reconfigure(line_buffering=True)
    except Exception as e:
        log.warning("启用行缓冲 stdout 失败：%s", e)


# ──────────────────────────────────────────────────────────────────
# Excel sheet 读取（轻量元信息）
# ──────────────────────────────────────────────────────────────────
def read_sheet_names(excel_path: Path | str) -> list[str]:
    """读取 Excel 的 sheet 列表。失败返回空列表（调用方判空决定后续）。"""
    path = Path(excel_path)
    if not path.is_file():
        log.error("Excel 文件不存在: %s", path)
        return []

    # 延迟导入 pandas —— 不强求纯 io 操作也加载数百 MB 内存
    try:
        import pandas as pd
    except ImportError as e:
        log.error("缺失 pandas，无法读取 Excel sheet 列表: %s", e)
        return []

    try:
        with pd.ExcelFile(path) as xl:
            return [str(s) for s in xl.sheet_names]
    except Exception as e:
        log.exception("读取 Excel sheet 列表失败 (%s): %s", path.name, e)
        return []


# ──────────────────────────────────────────────────────────────────
# Windows 系统调用
# ──────────────────────────────────────────────────────────────────
def kill_winword_processes(reason: str = "") -> None:
    """强制结束所有 WINWORD.EXE，避免 COM 附着到挂着隐藏弹窗的僵尸 Word。

    会顺带杀掉用户正在用的 Word！调用方需要在文档里提示用户先存盘。
    """
    if os.name != "nt":
        log.debug("非 Windows 平台，跳过 kill_winword_processes")
        return

    tag = f"（{reason}）" if reason else ""
    log.info("正在清理残留 WINWORD.EXE 进程%s ...", tag)

    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "WINWORD.EXE", "/T"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("taskkill 超时（10s），可能有进程被锁定")
        return
    except FileNotFoundError as e:
        log.error("找不到 taskkill 命令（非 Windows？）：%s", e)
        return

    if result.returncode == 0:
        log.info("已结束残留 Word 进程")
    elif result.returncode in (1, 128):
        # taskkill 在「无匹配进程」时返回 1（中文 Windows）或 128
        log.info("没有发现需要清理的 Word 进程")
    else:
        log.warning("taskkill 返回 %s: stderr=%s", result.returncode, (result.stderr or "").strip())


def unblock_file(file_path: Path | str) -> None:
    """移除 Windows 的「来自互联网」标记 (Zone.Identifier ADS)。

    对来自网盘 / 邮件 / 浏览器下载的文件特别有用 —— 否则 Word.Open 可能
    挂在受保护视图上。
    """
    if os.name != "nt":
        log.debug("非 Windows 平台，跳过 unblock_file")
        return

    abs_path = str(Path(file_path).resolve())

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f'Unblock-File -LiteralPath "{abs_path}"'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("Unblock-File 超时 (%s)", abs_path)
        return
    except FileNotFoundError as e:
        log.warning("找不到 powershell 命令：%s", e)
        return

    if result.returncode == 0:
        log.info("已解除文件网络标记: %s", Path(abs_path).name)
    else:
        # 通常是「文件本来就没标记」，warn 即可
        log.debug("Unblock-File 返回 %s: %s", result.returncode, (result.stderr or "").strip())


# ──────────────────────────────────────────────────────────────────
# 杂工
# ──────────────────────────────────────────────────────────────────
def ensure_extension(filename: str, allowed: tuple[str, ...], default: str | None = None) -> str:
    """如果文件名后缀不在允许列表里，补上 default（或 allowed[0]）。"""
    if filename.lower().endswith(allowed):
        return filename
    return filename + (default or allowed[0])
