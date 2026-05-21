"""api handlers (workspace / files) + 端到端 dispatch 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from civ_core.api import handlers
from civ_core.api.handlers import files as files_handler
from civ_core.api.handlers import leeb as leeb_handler
from civ_core.api.handlers import pdf_tools as pdf_handler
from civ_core.api.handlers import plot_curves as plot_handler
from civ_core.api.handlers import word2pdf as word2pdf_handler
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
    """build_dispatcher 注册了 workspace/files/plot_curves 全部方法 + ping/version。"""
    from civ_core.api.__main__ import build_dispatcher

    d = build_dispatcher()
    methods = d.methods()
    # 关键方法都在
    for m in (
        "ping",
        "version",
        "workspace.last",
        "workspace.set",
        "files.list_dir",
        "plot_curves.list_presets",
        "plot_curves.run",
    ):
        assert m in methods


def test_dispatcher_only_exposes_whitelisted_methods() -> None:
    """register_module 必须只暴露 __all__ 里的方法 —— 避免顶部 import 的
    工具类（Path / dataclass / 业务函数）被误注册成 RPC 方法，造成边界泄漏。"""
    from civ_core.api.__main__ import build_dispatcher

    d = build_dispatcher()
    methods = set(d.methods())
    # 这些是模块顶部 import 进来的，绝不能被注册成 RPC
    forbidden = {
        "workspace.Path",
        "workspace.create_standard_structure",
        "files.Path",
        "plot_curves.Path",
        "plot_curves.PlotCurvesError",
        "plot_curves.get_preset_names",
        "plot_curves.load_presets",
        "plot_curves.run_plot_curves",
    }
    leaked = forbidden & methods
    assert not leaked, f"非业务方法被泄漏为 RPC: {leaked}"


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
    assert hasattr(handlers, "plot_curves")


# ── plot_curves handler ───────────────────────────────────
def test_plot_curves_list_presets_shape() -> None:
    """list_presets 返回 {presets:[str], default:str|None}；预设库应不为空（系统预设至少 1 条）。"""
    res = plot_handler.list_presets()
    assert isinstance(res["presets"], list)
    assert all(isinstance(n, str) for n in res["presets"])
    # 系统至少有一条预设（healthcheck 验过）
    assert len(res["presets"]) >= 1
    assert res["default"] == res["presets"][0]


def test_plot_curves_run_rejects_missing_preset(tmp_path) -> None:
    """跑不存在的预设 → PlotCurvesError（dispatcher 会包成 -32603）。"""
    from civ_core.core.plot_curves import PlotCurvesError

    fake_xlsx = tmp_path / "x.xlsx"
    fake_xlsx.write_bytes(b"not a real xlsx")  # 不会真的去读到这一步
    with pytest.raises(PlotCurvesError):
        plot_handler.run(
            excel_path=str(fake_xlsx),
            preset="不存在的预设名",
            output_dir=str(tmp_path / "out"),
        )


def test_plot_curves_render_preview_missing_excel(tmp_path) -> None:
    """render_preview 缺 excel → 抛错（不静默返回空字节）。"""
    bad_preset = {
        "id_column": "X",
        "filename_template": "{id}.png",
        "title_template": "{id}",
        "x_axis": {"label": "x", "range": None},
        "y_axis": {"label": "y", "range": None},
        "curves": [],
    }
    with pytest.raises(Exception):
        plot_handler.render_preview(bad_preset, str(tmp_path / "nope.xlsx"))


def test_plot_curves_render_preview_returns_row_data(tmp_path) -> None:
    """render_preview 必须返回当前 row 的所有列值（之前用 stem 反查 id 永远空）。"""
    from openpyxl import Workbook

    xlsx = tmp_path / "data.xlsx"
    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.append(["编号", "X值", "Y值", "备注"])
    ws.append(["A1", 1.0, 10.0, "first"])
    ws.append(["A2", 2.0, 20.0, "second"])
    wb.save(str(xlsx))

    # filename_template 含中文后缀 —— stem 不等于 id，原 bug 就是这里失配
    preset = {
        "id_column": "编号",
        "filename_template": "{id}_曲线.png",
        "title_template": "{id} 预览",
        "x_axis": {"label": "X", "range": None},
        "y_axis": {"label": "Y", "range": None},
        "curves": [
            {
                "name": "曲线",
                "color": "#1F4FE0",
                "marker": "o",
                "linewidth": 2.0,
                "markersize": 6,
                "points": [
                    {"fixed_axis": "x", "fixed_value": 1.0, "var_column": "Y值"},
                ],
            }
        ],
    }
    # 第 0 张（A1）的 row_data 应该非空且含原始列
    res0 = plot_handler.render_preview(preset, str(xlsx), row_index=0)
    assert res0["row_data"], "row_data 不能为空 dict"
    assert res0["row_data"]["编号"] == "A1"
    assert res0["row_data"]["X值"] == 1.0
    assert res0["row_data"]["备注"] == "first"

    # 第 1 张（A2）应该是另一行
    res1 = plot_handler.render_preview(preset, str(xlsx), row_index=1)
    assert res1["row_data"]["编号"] == "A2"
    assert res1["row_data"]["备注"] == "second"


def test_plot_curves_render_preview_returns_base64_png(tmp_path) -> None:
    """端到端：写一个最小 xlsx + 最小预设 → 拿到非空 base64 PNG。"""
    import base64

    from openpyxl import Workbook

    xlsx = tmp_path / "data.xlsx"
    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.append(["编号", "X值", "Y值"])
    ws.append(["A1", 1.0, 10.0])
    ws.append(["A2", 2.0, 20.0])
    wb.save(str(xlsx))

    preset = {
        "id_column": "编号",
        "filename_template": "{id}.png",
        "title_template": "{id} 预览",
        "x_axis": {"label": "X", "range": None},
        "y_axis": {"label": "Y", "range": None},
        "curves": [
            {
                "name": "曲线",
                "color": "#1F4FE0",
                "marker": "o",
                "linewidth": 2.0,
                "markersize": 6,
                "points": [
                    {"fixed_axis": "x", "fixed_value": 1.0, "var_column": "Y值"},
                ],
            }
        ],
    }
    res = plot_handler.render_preview(preset, str(xlsx))
    assert res["mime"] == "image/png"
    assert res["total_rows"] == 2
    # base64 解出来必须是有效 PNG（前 8 字节为 PNG 魔数）
    raw = base64.b64decode(res["png_base64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_plot_curves_run_default_output_dir(tmp_path, monkeypatch) -> None:
    """output_dir=None 时默认 <excel 同级>/曲线图/。通过 mock run_plot_curves 验路径计算。"""
    from civ_core.api.handlers import plot_curves as ph
    from civ_core.core.plot_curves import RunResult

    excel = tmp_path / "data.xlsx"
    excel.write_bytes(b"")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        # 返回空结果即可
        from civ_core.core.plot_curves import BuildSummary

        return RunResult(
            written=[],
            failed=[],
            summary=BuildSummary(total_rows=0, skipped_empty_id=[], skipped_bad_data=[]),
        )

    monkeypatch.setattr(ph, "run_plot_curves", fake_run)
    ph.run(excel_path=str(excel), preset="x")  # output_dir 省略
    assert captured["output_dir"] == excel.parent / "曲线图"


# ── leeb handler ──────────────────────────────────────────
def _make_leeb_preview_xlsx(path: Path, n_rows: int = 5) -> None:
    """造一个最小可读 xlsx：1 行表头 + n 行数据。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["构件编号", "测点1", "测点2", "备注"])
    for i in range(n_rows):
        ws.append([f"G{i + 1}", 720.0 + i, 715.0 + i, ""])
    wb.save(str(path))


def test_leeb_preview_excel_basic(tmp_path) -> None:
    """preview_excel 返 sheets + 实际 sheet 名 + headers + 截断 rows + 总行数。"""
    xlsx = tmp_path / "data.xlsx"
    _make_leeb_preview_xlsx(xlsx, n_rows=3)
    res = leeb_handler.preview_excel(str(xlsx))
    assert isinstance(res["sheets"], list)
    assert res["sheet"] == res["sheets"][0]
    assert res["headers"] == ["构件编号", "测点1", "测点2", "备注"]
    assert res["total_rows"] == 3
    assert res["shown_rows"] == 3
    assert res["rows"][0]["构件编号"] == "G1"
    assert res["rows"][0]["测点1"] == 720.0


def test_leeb_preview_excel_sheet_fallback(tmp_path) -> None:
    """传不存在的 sheet → 回退到第一个，不抛错。"""
    xlsx = tmp_path / "data.xlsx"
    _make_leeb_preview_xlsx(xlsx, n_rows=1)
    res = leeb_handler.preview_excel(str(xlsx), sheet="不存在的sheet")
    assert res["sheet"] == res["sheets"][0]


def test_leeb_preview_excel_caps_max_rows(tmp_path) -> None:
    """max_rows 截断生效，total_rows 仍为真实总数。"""
    xlsx = tmp_path / "data.xlsx"
    _make_leeb_preview_xlsx(xlsx, n_rows=50)
    res = leeb_handler.preview_excel(str(xlsx), max_rows=10)
    assert res["total_rows"] == 50
    assert res["shown_rows"] == 10
    assert len(res["rows"]) == 10


def test_leeb_preview_excel_exposes_in_all() -> None:
    """preview_excel 必须在 __all__ 里，否则 register_module 不会暴露成 RPC。"""
    assert "preview_excel" in leeb_handler.__all__


# ── pdf_tools handler ─────────────────────────────────────
def _make_blank_pdf(out_path: Path, n_pages: int) -> Path:
    """造一个 n 页空白 PDF 供测试用。"""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=595, height=842)
    with out_path.open("wb") as fh:
        writer.write(fh)
    writer.close()
    return out_path


def test_pdf_inspect_basic(tmp_path) -> None:
    """inspect 返每个 PDF 的页数 + 大小 + 合计 total_pages。"""
    a = _make_blank_pdf(tmp_path / "a.pdf", n_pages=3)
    b = _make_blank_pdf(tmp_path / "b.pdf", n_pages=7)
    res = pdf_handler.inspect([str(a), str(b)])
    assert res["total_pages"] == 10
    assert len(res["files"]) == 2
    assert res["files"][0]["pages"] == 3
    assert res["files"][1]["pages"] == 7
    assert res["files"][0]["size_kb"] > 0
    assert "error" not in res["files"][0]


def test_pdf_inspect_missing_file(tmp_path) -> None:
    """单个文件不存在 → 带 error 字段返回，不影响其他文件统计。"""
    a = _make_blank_pdf(tmp_path / "a.pdf", n_pages=2)
    res = pdf_handler.inspect([str(a), str(tmp_path / "ghost.pdf")])
    assert res["total_pages"] == 2  # 只算成功的
    assert "error" in res["files"][1]
    assert "不存在" in res["files"][1]["error"]
    assert "pages" not in res["files"][1]


def test_pdf_inspect_exposes_in_all() -> None:
    assert "inspect" in pdf_handler.__all__


# ── word2pdf handler ──────────────────────────────────────
def _make_simple_docx(out_path: Path, n_paragraphs: int) -> Path:
    """造一个有 n 段的简单 docx 供测试。python-docx 生成的不含 Pages 缓存。"""
    from docx import Document

    doc = Document()
    for i in range(n_paragraphs):
        doc.add_paragraph(f"段落 {i + 1}")
    doc.save(str(out_path))
    return out_path


def test_word2pdf_inspect_basic(tmp_path) -> None:
    """inspect 返每个 docx 的 size_kb + paragraphs；纯 python-docx 生成不含 pages。"""
    a = _make_simple_docx(tmp_path / "a.docx", n_paragraphs=5)
    b = _make_simple_docx(tmp_path / "b.docx", n_paragraphs=12)
    res = word2pdf_handler.inspect([str(a), str(b)])
    assert len(res["files"]) == 2
    assert res["files"][0]["paragraphs"] == 5
    assert res["files"][1]["paragraphs"] == 12
    assert res["files"][0]["size_kb"] > 0
    assert "error" not in res["files"][0]


def test_word2pdf_inspect_missing_file(tmp_path) -> None:
    """单文件不存在 → 带 error 字段，不影响其他统计。"""
    a = _make_simple_docx(tmp_path / "a.docx", n_paragraphs=3)
    res = word2pdf_handler.inspect([str(a), str(tmp_path / "ghost.docx")])
    assert res["files"][0]["paragraphs"] == 3
    assert "error" in res["files"][1]
    assert "不存在" in res["files"][1]["error"]


def test_word2pdf_inspect_exposes_in_all() -> None:
    assert "inspect" in word2pdf_handler.__all__
