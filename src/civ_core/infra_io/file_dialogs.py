"""PySide6 文件 / 目录对话框 —— 唯一允许在 io/ 层使用 Qt 的地方。

为什么单独成文件？
  • io/io_helpers.py 是纯 Python，被很多 core 算法 import；
    一旦它依赖 PySide6，core 就被迫拖上 GUI 库。
  • 把 Qt 文件对话框关进这个文件，调用方明确意识到「这一步会弹窗」。
  • UI 层若要拿到选中路径，应当通过 service 层（不是直接调这个）；
    本文件主要给「子进程独立工具脚本」（Stage 2/5）使用。

工程规范落地：
  ✓ ensure_app() 幂等，subprocess 中安全反复调
  ✓ logger 记录用户取消 / 选中路径
  ✓ 不返回空字符串歧义 —— 取消时返回 None，类型清晰
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# QApplication 单例守门员
# ──────────────────────────────────────────────────────────────────
def ensure_app() -> QApplication:
    """子进程脚本调对话框前先调它；幂等。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else [""])
        log.debug("创建子进程级 QApplication 实例")
    return app


# ──────────────────────────────────────────────────────────────────
# 文件 / 目录选择
# ──────────────────────────────────────────────────────────────────
def pick_open_file(
    title: str = "选择文件",
    filters: list[tuple[str, str]] | None = None,
    start_dir: Path | str = "",
) -> Path | None:
    """打开「打开文件」对话框。用户取消返回 None。

    filters 形如 [("Excel 文件", "*.xlsx *.xlsm"), ("所有文件", "*.*")]
    """
    ensure_app()
    filter_str = _build_filter_string(filters)
    path, _ = QFileDialog.getOpenFileName(None, title, str(start_dir), filter_str)
    if not path:
        log.debug("用户取消了 [%s]", title)
        return None
    log.info("用户选择文件 [%s]: %s", title, path)
    return Path(path)


def pick_save_file(
    title: str = "保存为",
    filters: list[tuple[str, str]] | None = None,
    start_dir: Path | str = "",
    default_name: str = "",
) -> Path | None:
    """打开「保存文件」对话框。用户取消返回 None。"""
    ensure_app()
    filter_str = _build_filter_string(filters)
    initial = str(Path(start_dir) / default_name) if default_name else str(start_dir)
    path, _ = QFileDialog.getSaveFileName(None, title, initial, filter_str)
    if not path:
        log.debug("用户取消了 [%s]", title)
        return None
    log.info("用户选择保存路径 [%s]: %s", title, path)
    return Path(path)


def pick_directory(
    title: str = "选择目录",
    start_dir: Path | str = "",
) -> Path | None:
    """打开「选择目录」对话框。用户取消返回 None。"""
    ensure_app()
    path = QFileDialog.getExistingDirectory(None, title, str(start_dir))
    if not path:
        log.debug("用户取消了 [%s]", title)
        return None
    log.info("用户选择目录 [%s]: %s", title, path)
    return Path(path)


def pick_excel_file(title: str = "选择 Excel 文件") -> Path | None:
    """便捷封装：选 Excel。"""
    return pick_open_file(
        title=title,
        filters=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")],
    )


def pick_word_file(title: str = "选择 Word 文档") -> Path | None:
    """便捷封装：选 Word。"""
    return pick_open_file(
        title=title,
        filters=[("Word 文档", "*.docx *.doc"), ("所有文件", "*.*")],
    )


# ──────────────────────────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────────────────────────
def _build_filter_string(filters: list[tuple[str, str]] | None) -> str:
    """[("Excel 文件", "*.xlsx"), ...] → "Excel 文件 (*.xlsx);;..." """
    if not filters:
        return "所有文件 (*.*)"
    return ";;".join(f"{label} ({patt})" for label, patt in filters)
