"""infra_io/word_to_pdf.py 单元测试。

测试策略：
  • 不真启 Word/WPS COM（CI 没装 Office、单测应快）
  • 用 monkeypatch 替换 _mount_engine + _convert_one_with_app 模拟 COM
  • 同时验证 try/finally 释放：哪怕单文件 raise，COM 也得 Quit
  • progress_cb 抛异常不能拖垮批量
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def fake_pythoncom(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """替换 pythoncom 模块为不做事的 stub。

    convert_one / convert_batch 在内部 import pythoncom，monkeypatch
    sys.modules 即可拦截。stats 字典让测试断言 init/uninit 配对。
    """
    stats = {"init": 0, "uninit": 0}

    fake = ModuleType("pythoncom")
    fake.CoInitialize = lambda: stats.__setitem__("init", stats["init"] + 1)  # type: ignore[attr-defined]
    fake.CoUninitialize = lambda: stats.__setitem__(  # type: ignore[attr-defined]
        "uninit", stats["uninit"] + 1
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake)
    return stats


class _FakeApp:
    """模拟 Word.Application COM 对象，记录调用。"""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.visible = False
        self.display_alerts = 0
        self.quit_called = 0
        self._fail_on = fail_on or set()
        self.Documents = _FakeDocuments(self._fail_on)

    @property
    def Visible(self) -> bool:
        return self.visible

    @Visible.setter
    def Visible(self, v: bool) -> None:
        self.visible = v

    @property
    def DisplayAlerts(self) -> int:
        return self.display_alerts

    @DisplayAlerts.setter
    def DisplayAlerts(self, v: int) -> None:
        self.display_alerts = v

    def Quit(self) -> None:
        self.quit_called += 1


class _FakeDocuments:
    def __init__(self, fail_on: set[str]) -> None:
        self._fail_on = fail_on

    def Open(self, path: str, ReadOnly: int = 0) -> Any:  # noqa: N803
        name = Path(path).name
        if name in self._fail_on:
            raise RuntimeError(f"模拟打开失败：{name}")
        return _FakeDoc(name, self._fail_on)


class _FakeDoc:
    def __init__(self, name: str, fail_on: set[str]) -> None:
        self.name = name
        self._fail_on = fail_on
        self.close_called = 0
        self.saved_to: str | None = None

    def SaveAs(self, path: str, FileFormat: int = 17) -> None:  # noqa: N803
        if f"saveas:{self.name}" in self._fail_on:
            raise RuntimeError(f"模拟 SaveAs 失败：{self.name}")
        # 实际落盘：写一个最小的 dummy PDF
        Path(path).write_bytes(b"%PDF-1.4 fake pdf for test\n%%EOF")
        self.saved_to = path

    def Close(self, _save: int = 0) -> None:
        self.close_called += 1


def _make_docx(path: Path) -> Path:
    """造一个占位"docx"文件（实际只是占位字节，本测试不真解析）。"""
    path.write_bytes(b"PK fake docx")
    return path


# ──────────────────────────────────────────────────────────────────
# convert_one
# ──────────────────────────────────────────────────────────────────
class TestConvertOne:
    def test_basic_success(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_pythoncom: dict[str, int],
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        fake = _FakeApp()
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        src = _make_docx(tmp_path / "doc.docx")
        out_dir = tmp_path / "out"
        result = word_to_pdf.convert_one(src, out_dir)

        assert result == out_dir / "doc.pdf"
        assert result.is_file()
        # COM 生命周期：Init/Uninit 都被调用 1 次
        assert fake_pythoncom["init"] == 1
        assert fake_pythoncom["uninit"] == 1
        # COM Quit 被调用
        assert fake.quit_called == 1

    def test_missing_input_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_pythoncom: dict[str, int],
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        fake = _FakeApp()
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        with pytest.raises(word_to_pdf.Word2PdfError, match="不存在"):
            word_to_pdf.convert_one(tmp_path / "nope.docx", tmp_path)

        # 即使失败也要释放 COM
        assert fake_pythoncom["uninit"] == 1
        assert fake.quit_called == 1

    def test_saveas_failure_propagates_and_releases(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_pythoncom: dict[str, int],
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        src = _make_docx(tmp_path / "doc.docx")
        # SaveAs 失败
        fake = _FakeApp(fail_on={"saveas:doc.docx"})
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        with pytest.raises(word_to_pdf.Word2PdfError, match="转换失败"):
            word_to_pdf.convert_one(src, tmp_path / "out")

        assert fake_pythoncom["uninit"] == 1
        assert fake.quit_called == 1


# ──────────────────────────────────────────────────────────────────
# convert_batch
# ──────────────────────────────────────────────────────────────────
class TestConvertBatch:
    def test_all_success(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_pythoncom: dict[str, int],
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        fake = _FakeApp()
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        inputs = [_make_docx(tmp_path / f"f{i}.docx") for i in range(3)]
        out_dir = tmp_path / "out"
        result = word_to_pdf.convert_batch(inputs, out_dir)

        assert len(result.written) == 3
        assert len(result.failed) == 0
        for p in result.written:
            assert p.is_file()
        # 一个 COM 进程，1 次 Init/Uninit/Quit
        assert fake_pythoncom["init"] == 1
        assert fake_pythoncom["uninit"] == 1
        assert fake.quit_called == 1

    def test_partial_failure_records(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        inputs = [_make_docx(tmp_path / f"f{i}.docx") for i in range(3)]
        # f1 SaveAs 失败
        fake = _FakeApp(fail_on={"saveas:f1.docx"})
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        result = word_to_pdf.convert_batch(inputs, tmp_path / "out")
        assert len(result.written) == 2
        assert len(result.failed) == 1
        # 失败项是 f1.docx
        assert result.failed[0][0].name == "f1.docx"

    def test_progress_cb_called_per_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        fake = _FakeApp()
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        inputs = [_make_docx(tmp_path / f"f{i}.docx") for i in range(3)]
        seen: list[tuple[int, int, str]] = []
        word_to_pdf.convert_batch(
            inputs,
            tmp_path / "out",
            progress_cb=lambda done, total, cur: seen.append((done, total, cur.name)),
        )
        assert seen == [
            (1, 3, "f0.docx"),
            (2, 3, "f1.docx"),
            (3, 3, "f2.docx"),
        ]

    def test_progress_cb_exception_does_not_break_batch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        fake = _FakeApp()
        monkeypatch.setattr(word_to_pdf, "_mount_engine", lambda: (fake, "fake"))

        inputs = [_make_docx(tmp_path / f"f{i}.docx") for i in range(3)]

        def bad_cb(done: int, total: int, cur: Path) -> None:
            raise RuntimeError("回调炸了")

        # 不应抛出（被 word_to_pdf 内部吞掉 + warn）
        result = word_to_pdf.convert_batch(inputs, tmp_path / "out", progress_cb=bad_cb)
        assert len(result.written) == 3

    def test_empty_inputs_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        # 即使引擎都没挂上，空列表应被前置拦下
        monkeypatch.setattr(
            word_to_pdf,
            "_mount_engine",
            lambda: (_FakeApp(), "should-not-be-called"),
        )

        with pytest.raises(word_to_pdf.Word2PdfError, match="为空"):
            word_to_pdf.convert_batch([], tmp_path / "out")


# ──────────────────────────────────────────────────────────────────
# COM 释放保证：_mount_engine 失败也不能漏 CoUninitialize
# ──────────────────────────────────────────────────────────────────
class TestComLifecycle:
    def test_mount_failure_still_uninit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_pythoncom: dict[str, int],
    ) -> None:
        from civ_core.infra_io import word_to_pdf

        def bad_mount() -> Any:
            raise word_to_pdf.Word2PdfError("模拟挂载失败")

        monkeypatch.setattr(word_to_pdf, "_mount_engine", bad_mount)

        with pytest.raises(word_to_pdf.Word2PdfError, match="挂载失败"):
            word_to_pdf.convert_one(tmp_path / "x.docx", tmp_path)

        # 关键：CoUninitialize 必须配对
        assert fake_pythoncom["init"] == 1
        assert fake_pythoncom["uninit"] == 1
