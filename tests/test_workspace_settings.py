"""workspace_settings：last_workspace 路径持久化 round-trip + 失效降级。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

# QSettings 不强制要 QApplication，但 offscreen 平台早设上避免后续 UI 用例联动报错
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from civ_core.infra_io import workspace_settings as ws  # noqa: E402


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """把 QSettings 后端切到 tmp_path 下的 ini 文件，避免污染用户家目录或被其他测试串扰。"""
    ini = tmp_path / "ws.ini"

    def _factory() -> QSettings:
        return QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr(ws, "_make_settings", _factory)
    yield


def test_load_none_when_unset(isolated_settings) -> None:
    """空 store → load 应返回 None。"""
    assert ws.load_last_workspace() is None


def test_roundtrip(isolated_settings, tmp_path: Path) -> None:
    """save 后 load 应拿到同一路径。"""
    p = tmp_path / "ws_a"
    p.mkdir()
    ws.save_last_workspace(p)
    got = ws.load_last_workspace()
    assert got == p


def test_load_none_when_path_gone(isolated_settings, tmp_path: Path) -> None:
    """save 后该路径被删除 → load 应降级为 None（不抛）。"""
    p = tmp_path / "ws_gone"
    p.mkdir()
    ws.save_last_workspace(p)
    p.rmdir()
    assert ws.load_last_workspace() is None


def test_clear(isolated_settings, tmp_path: Path) -> None:
    """clear 后 load 应返回 None。"""
    p = tmp_path / "ws_clear"
    p.mkdir()
    ws.save_last_workspace(p)
    ws.clear_last_workspace()
    assert ws.load_last_workspace() is None


def test_load_ignores_file_path(isolated_settings, tmp_path: Path) -> None:
    """若 store 里残留的是文件而非目录路径 → load 应返回 None。"""
    f = tmp_path / "is_file.txt"
    f.write_text("x")
    # 直接走工厂写入一个文件路径，模拟脏数据
    s = ws._make_settings()
    s.setValue(ws._KEY, str(f))
    s.sync()
    assert ws.load_last_workspace() is None
