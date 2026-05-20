"""工作区（last_workspace）持久化（QSettings 包装）。

为什么独立：
  - shell / 启动门槛 / 工具页都要读"当前工作区"，集中一处避免 key 字符串散落
  - QSettings("ZGQ", "CivCore") 与 main_window 的窗口几何同 store
  - 失效降级（路径被用户删/移动后）由本模块统一处理，调用方只关心"能不能拿到合法 Path"

测试切后端：暴露 `_make_settings()` 工厂，测试 monkeypatch 它来把 store
重定向到 tmp_path / ini 文件，避免污染真实用户家目录或被其他测试串扰。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

# 与 main_window/QSettings 共用同一个 (org, app) 命名空间
_ORG = "ZGQ"
_APP = "CivCore"
_KEY = "workspace/last_folder"


def _make_settings() -> QSettings:
    """工厂方法：测试通过 monkeypatch 此函数把 store 重定向到临时位置。"""
    return QSettings(_ORG, _APP)


def load_last_workspace() -> Path | None:
    """读取上次工作区路径；不存在 / 路径已失效 / 是文件而非目录 → 一律返回 None。"""
    s = _make_settings()
    raw = s.value(_KEY)
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_dir():
        return None
    return p


def save_last_workspace(path: Path) -> None:
    """写入当前工作区路径。"""
    s = _make_settings()
    s.setValue(_KEY, str(Path(path)))
    s.sync()


def clear_last_workspace() -> None:
    """清掉记忆（测试 / 用户主动清理用）。"""
    s = _make_settings()
    s.remove(_KEY)
    s.sync()
