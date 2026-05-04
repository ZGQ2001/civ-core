"""UI 层快捷工厂：把"选 sheet / 选列名 / 选 Word / 选输出位置"这种重复的 form schema 抽出来。

具体的对话框还是用 ui_components.ModernDynamicFormDialog —— 这里只生成它的入参。
"""

import os
from typing import Any


def field_sheet_select(sheet_names: list[str], default: str | None = None) -> dict[str, Any]:
    return {
        "key": "sheet_name",
        "label": "Excel 工作表:",
        "type": "select",
        "options": sheet_names,
        "default": default or (sheet_names[0] if sheet_names else ""),
    }


def field_text(key: str, label: str, default: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "type": "text", "default": default}


def field_word_file(
    key: str = "word_path", label: str = "Word 文件:", default: str = ""
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": "file",
        "file_types": [("Word 文件", "*.docx"), ("所有文件", "*.*")],
        "default": default,
    }


def field_dir(
    key: str = "output_dir", label: str = "输出目录:", default: str = ""
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": "dir",
        "default": default or os.getcwd(),
    }
