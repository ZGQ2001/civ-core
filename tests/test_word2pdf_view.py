"""Word2PdfView 烟雾测试（结构 + 校验分支）。

不测真实 COM；convert_batch 在 test_word_to_pdf.py 已覆盖。
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
    class _Cfg:
        pass

    return _Cfg()


class TestStructure:
    def test_object_name(self, qapp: QApplication) -> None:
        from civ_core.ui.windows.word2pdf_view import Word2PdfView

        view = Word2PdfView(_make_cfg())  # type: ignore[arg-type]
        try:
            assert view.objectName() == "word2PdfPage"
        finally:
            view.deleteLater()


class TestValidation:
    def test_empty_inputs_does_not_start(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from civ_core.ui.windows import word2pdf_view as w2v

        starts: list[bool] = []
        # 投递点是 self._pool.start(worker)，patch 它
        monkeypatch.setattr(
            "PySide6.QtCore.QThreadPool.start",
            lambda self, *a, **k: starts.append(True),
        )

        view = w2v.Word2PdfView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._on_run()
            assert starts == []
        finally:
            view.deleteLater()

    def test_missing_out_dir_blocks(
        self, qapp: QApplication, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.ui.windows import word2pdf_view as w2v

        starts: list[bool] = []
        monkeypatch.setattr(
            "PySide6.QtCore.QThreadPool.start",
            lambda self, *a, **k: starts.append(True),
        )

        view = w2v.Word2PdfView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._inputs = [tmp_path / "a.docx"]
            view._out_dir = None
            view._on_run()
            assert starts == []
        finally:
            view.deleteLater()

    def test_valid_inputs_starts_worker(
        self, qapp: QApplication, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.ui.windows import word2pdf_view as w2v

        starts: list[bool] = []
        monkeypatch.setattr(
            "PySide6.QtCore.QThreadPool.start",
            lambda self, *a, **k: starts.append(True),
        )

        view = w2v.Word2PdfView(_make_cfg())  # type: ignore[arg-type]
        try:
            view._inputs = [tmp_path / "a.docx"]
            view._out_dir = tmp_path
            view._on_run()
            assert starts == [True]
        finally:
            view.deleteLater()
