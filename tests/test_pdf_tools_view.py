"""PdfToolsView 烟雾测试（仅基本结构 + 校验分支）。

不测的内容：
  • 真实 QFileDialog（依赖系统弹窗）
  • 真实 worker 落盘（pdf_io 已在 test_pdf_io.py 覆盖）

测的内容：
  • 视图能创建 / objectName 与 main_window 路由约定一致
  • 合并 Tab：少于 2 个文件 / 无输出 → 弹 warning，不启 worker
  • 拆分 Tab：缺输入 / 无输出 → 弹 warning，不启 worker
  • 拆分模式切换 → 范围 LineEdit 启用/禁用
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app  # type: ignore[return-value]


def _make_cfg() -> object:
    """轻量假 AppConfig：PdfToolsView 当前只读 self._cfg 占位，未访问字段。"""

    class _Cfg:
        pass

    return _Cfg()


class TestStructure:
    def test_object_name_matches_routing(self, qapp: QApplication) -> None:
        from civ_core.ui.windows.pdf_tools_view import PdfToolsView

        view = PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            assert view.objectName() == "pdfToolsPage"
        finally:
            view.deleteLater()

    def test_starts_with_merge_tab(self, qapp: QApplication) -> None:
        from civ_core.ui.windows.pdf_tools_view import PdfToolsView

        view = PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            assert view._stack.currentIndex() == 0
        finally:
            view.deleteLater()


class TestMergeValidation:
    def test_empty_inputs_blocks_with_warning(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """合并列表为空 → _on_merge_run 应不启 worker。"""
        from civ_core.ui.windows import pdf_tools_view as ptv

        starts: list[bool] = []
        monkeypatch.setattr(
            ptv.PdfToolsView,
            "_launch_worker",
            lambda *a, **kw: starts.append(True),
        )

        view = ptv.PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._on_merge_run()  # 列表空
            assert starts == []
        finally:
            view.deleteLater()

    def test_single_file_blocks(
        self, qapp: QApplication, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """只 1 个文件也不让合并。"""
        from civ_core.ui.windows import pdf_tools_view as ptv

        starts: list[bool] = []
        monkeypatch.setattr(
            ptv.PdfToolsView,
            "_launch_worker",
            lambda *a, **kw: starts.append(True),
        )

        view = ptv.PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._merge_inputs = [tmp_path / "a.pdf"]
            view._merge_out_path = tmp_path / "out.pdf"
            view._on_merge_run()
            assert starts == []
        finally:
            view.deleteLater()

    def test_missing_out_path_blocks(
        self, qapp: QApplication, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.ui.windows import pdf_tools_view as ptv

        starts: list[bool] = []
        monkeypatch.setattr(
            ptv.PdfToolsView,
            "_launch_worker",
            lambda *a, **kw: starts.append(True),
        )

        view = ptv.PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._merge_inputs = [
                tmp_path / "a.pdf", tmp_path / "b.pdf",
            ]
            view._merge_out_path = None
            view._on_merge_run()
            assert starts == []
        finally:
            view.deleteLater()


class TestSplitTab:
    def test_mode_toggle_enables_range_edit(
        self, qapp: QApplication
    ) -> None:
        from civ_core.ui.windows.pdf_tools_view import PdfToolsView

        view = PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            # 默认 per_page，范围 LineEdit 禁用
            assert view._range_edit.isEnabled() is False
            # 切到范围模式
            view._mode_range.setChecked(True)
            assert view._range_edit.isEnabled() is True
        finally:
            view.deleteLater()

    def test_missing_input_blocks(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.ui.windows import pdf_tools_view as ptv

        starts: list[bool] = []
        monkeypatch.setattr(
            ptv.PdfToolsView,
            "_launch_worker",
            lambda *a, **kw: starts.append(True),
        )
        view = ptv.PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._on_split_run()
            assert starts == []
        finally:
            view.deleteLater()

    def test_range_mode_empty_expr_blocks(
        self, qapp: QApplication, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.ui.windows import pdf_tools_view as ptv

        starts: list[bool] = []
        monkeypatch.setattr(
            ptv.PdfToolsView,
            "_launch_worker",
            lambda *a, **kw: starts.append(True),
        )
        view = ptv.PdfToolsView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._split_input = tmp_path / "x.pdf"
            view._split_out_dir = tmp_path
            view._mode_range.setChecked(True)
            view._range_edit.setText("   ")
            view._on_split_run()
            assert starts == []
        finally:
            view.deleteLater()
