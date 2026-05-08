"""琐碎工具函数（时间转换、路径清洗等）。"""

import os


def ensure_extension(filename: str, allowed: tuple, default: str | None = None) -> str:
    """如果文件名后缀不在允许列表里，补上 default（或 allowed[0]）。"""
    if filename.lower().endswith(allowed):
        return filename
    return filename + (default or allowed[0])


def safe_filename(name: str) -> str:
    """把字符串里 Windows 不允许的文件名字符替换为下划线。"""
    invalid = r'\/:*?"<>|'
    for ch in invalid:
        name = name.replace(ch, "_")
    return name.strip()


def resolve_root() -> str:
    """返回项目根目录（src 的上级）。"""
    return str(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    )
