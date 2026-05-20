"""api handlers (workspace / files) + 端到端 dispatch 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from civ_core.api import handlers
from civ_core.api.handlers import files as files_handler
from civ_core.api.handlers import workspace as ws_handler


# ── workspace handler ─────────────────────────────────────
@pytest.fixture
def isolated_ws_store(tmp_path, monkeypatch):
    """把 workspace store 重定向到 tmp_path，避免污染用户 ~/.civ-core。"""
    monkeypatch.setattr(ws_handler, "_STORE", tmp_path / "workspace.json")


def test_workspace_last_empty(isolated_ws_store) -> None:
    assert ws_handler.last() == {"path": None}


def test_workspace_set_then_last(isolated_ws_store, tmp_path) -> None:
    p = tmp_path / "ws"
    p.mkdir()
    res = ws_handler.set(str(p))
    assert res["ok"] is True
    assert Path(res["path"]) == p
    assert Path(ws_handler.last()["path"]) == p


def test_workspace_set_rejects_non_dir(isolated_ws_store, tmp_path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        ws_handler.set(str(f))


def test_workspace_last_returns_none_if_path_gone(isolated_ws_store, tmp_path) -> None:
    p = tmp_path / "gone"
    p.mkdir()
    ws_handler.set(str(p))
    p.rmdir()
    assert ws_handler.last() == {"path": None}


def test_workspace_clear(isolated_ws_store, tmp_path) -> None:
    p = tmp_path / "ws"
    p.mkdir()
    ws_handler.set(str(p))
    ws_handler.clear()
    assert ws_handler.last() == {"path": None}


def test_workspace_create_standard(isolated_ws_store, tmp_path) -> None:
    res = ws_handler.create_standard(str(tmp_path), "新项目")
    root = Path(res["path"])
    assert root.is_dir()
    # 标准骨架就位
    for sub in ("委托方提供资料", "数据", "报告", "模板", ".civ-core"):
        assert (root / sub).is_dir()


def test_workspace_create_standard_rejects_bad_name(isolated_ws_store, tmp_path) -> None:
    with pytest.raises(ValueError):
        ws_handler.create_standard(str(tmp_path), "")
    with pytest.raises(ValueError):
        ws_handler.create_standard(str(tmp_path), "bad/name")
    with pytest.raises(ValueError):
        ws_handler.create_standard(str(tmp_path), "bad\\name")


# ── files handler ─────────────────────────────────────
def test_list_dir_basic(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b.txt").write_text("hi")
    res = files_handler.list_dir(str(tmp_path))
    names = [e["name"] for e in res["entries"]]
    assert names == ["a", "b.txt"]  # 目录排前 + 字母序
    assert res["entries"][0]["is_dir"] is True
    assert res["entries"][1]["is_dir"] is False
    assert res["entries"][1]["size"] == 2


def test_list_dir_hides_civ_core_always(tmp_path) -> None:
    (tmp_path / ".civ-core").mkdir()
    (tmp_path / "visible").mkdir()
    res = files_handler.list_dir(str(tmp_path), show_hidden=True)
    names = [e["name"] for e in res["entries"]]
    assert "visible" in names
    assert ".civ-core" not in names, ".civ-core 即使 show_hidden=True 也必须隐藏"


def test_list_dir_hides_dotfiles_by_default(tmp_path) -> None:
    (tmp_path / ".gitignore").write_text("x")
    (tmp_path / "README.md").write_text("y")
    default = [e["name"] for e in files_handler.list_dir(str(tmp_path))["entries"]]
    assert ".gitignore" not in default
    shown = [
        e["name"]
        for e in files_handler.list_dir(str(tmp_path), show_hidden=True)["entries"]
    ]
    assert ".gitignore" in shown


def test_list_dir_rejects_non_dir(tmp_path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        files_handler.list_dir(str(f))


def test_exists(tmp_path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert files_handler.exists(str(f)) == {"exists": True, "is_dir": False, "is_file": True}
    assert files_handler.exists(str(tmp_path)) == {"exists": True, "is_dir": True, "is_file": False}
    assert files_handler.exists(str(tmp_path / "nope")) == {
        "exists": False,
        "is_dir": False,
        "is_file": False,
    }


# ── 端到端 dispatch + handler 注册 ───────────────────────
def test_full_dispatcher_methods(isolated_ws_store) -> None:
    """build_dispatcher 注册了 workspace/files 全部方法 + ping/version。"""
    from civ_core.api.__main__ import build_dispatcher

    d = build_dispatcher()
    methods = d.methods()
    # 关键方法都在
    for m in ("ping", "version", "workspace.last", "workspace.set", "files.list_dir"):
        assert m in methods


def test_ping_roundtrip_via_dispatcher() -> None:
    from civ_core.api.__main__ import build_dispatcher

    d = build_dispatcher()
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    resp = json.loads(d.handle_raw(req))
    assert resp["result"] == "pong"


def test_workspace_set_via_dispatcher(isolated_ws_store, tmp_path) -> None:
    from civ_core.api.__main__ import build_dispatcher

    d = build_dispatcher()
    p = tmp_path / "rpc_ws"
    p.mkdir()
    req = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "workspace.set",
            "params": {"path": str(p)},
        }
    )
    resp = json.loads(d.handle_raw(req))
    assert resp["result"]["ok"] is True
    assert Path(resp["result"]["path"]) == p


def test_handlers_module_exposes_submodules() -> None:
    assert hasattr(handlers, "workspace")
    assert hasattr(handlers, "files")
