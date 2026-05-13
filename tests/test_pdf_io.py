"""infra_io/pdf_io.py 单元测试（合并 / 拆分 / 表达式解析）。

测试策略：
  • parse_page_ranges 是纯函数 —— 不依赖任何文件，直接覆盖所有边界
  • merge / split 用 pypdf 自己造一份多页测试 PDF（tmp_path），
    然后断言写出的页数、文件存在性、跨平台路径
  • 不测视觉内容（像素差），只测页数与结构正确性
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter


def _make_test_pdf(out_path: Path, n_pages: int = 5) -> Path:
    """造一个 N 页空白 PDF 供测试用。每页 A4 大小，无内容。"""
    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=595, height=842)
    with out_path.open("wb") as fh:
        writer.write(fh)
    writer.close()
    return out_path


# ──────────────────────────────────────────────────────────────────
# parse_page_ranges
# ──────────────────────────────────────────────────────────────────
class TestParsePageRanges:
    def test_single_page(self) -> None:
        from civ_core.infra_io.pdf_io import parse_page_ranges

        assert parse_page_ranges("3", total_pages=10) == [(2, 3)]

    def test_range(self) -> None:
        from civ_core.infra_io.pdf_io import parse_page_ranges

        # 1-3 → 0-based 半开 (0, 3)
        assert parse_page_ranges("1-3", total_pages=10) == [(0, 3)]

    def test_mixed(self) -> None:
        from civ_core.infra_io.pdf_io import parse_page_ranges

        assert parse_page_ranges("1-3,5,7-9", total_pages=10) == [
            (0, 3),
            (4, 5),
            (6, 9),
        ]

    def test_whitespace_tolerance(self) -> None:
        from civ_core.infra_io.pdf_io import parse_page_ranges

        assert parse_page_ranges(" 1 - 3 , 5 ", total_pages=10) == [(0, 3), (4, 5)]

    def test_empty_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        for expr in ("", "   "):
            with pytest.raises(PdfOpError, match="不能为空"):
                parse_page_ranges(expr, total_pages=10)

    def test_zero_total_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        with pytest.raises(PdfOpError, match="任何页"):
            parse_page_ranges("1", total_pages=0)

    def test_invalid_token_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        for expr in ("abc", "1-2-3", "1.5", "1--3"):
            with pytest.raises(PdfOpError, match="无法解析"):
                parse_page_ranges(expr, total_pages=10)

    def test_empty_comma_token_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        with pytest.raises(PdfOpError, match="空项"):
            parse_page_ranges("1,,3", total_pages=10)

    def test_out_of_range_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        with pytest.raises(PdfOpError, match="超过"):
            parse_page_ranges("1-15", total_pages=10)
        with pytest.raises(PdfOpError, match="超过"):
            parse_page_ranges("99", total_pages=10)

    def test_zero_page_rejected(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        # 0 页不存在（PDF 1-based）
        with pytest.raises(PdfOpError, match=">= 1"):
            parse_page_ranges("0", total_pages=10)

    def test_reversed_range_raises(self) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, parse_page_ranges

        with pytest.raises(PdfOpError, match="颠倒"):
            parse_page_ranges("5-3", total_pages=10)


# ──────────────────────────────────────────────────────────────────
# merge_pdfs
# ──────────────────────────────────────────────────────────────────
class TestMergePdfs:
    def test_merge_two_pdfs(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import merge_pdfs

        a = _make_test_pdf(tmp_path / "a.pdf", n_pages=3)
        b = _make_test_pdf(tmp_path / "b.pdf", n_pages=4)
        out = tmp_path / "merged.pdf"

        result = merge_pdfs([a, b], out)
        assert result == out
        assert out.is_file()

        reader = PdfReader(str(out))
        assert len(reader.pages) == 7  # 3 + 4

    def test_merge_preserves_order(self, tmp_path: Path) -> None:
        """合并顺序应严格按 inputs 列表（断言总页数 + 顺序代表性）。"""
        from civ_core.infra_io.pdf_io import merge_pdfs

        pdfs = [
            _make_test_pdf(tmp_path / f"{i}.pdf", n_pages=i + 1) for i in range(3)
        ]  # 1, 2, 3 页
        out = tmp_path / "ordered.pdf"
        merge_pdfs(pdfs, out)

        reader = PdfReader(str(out))
        assert len(reader.pages) == 1 + 2 + 3  # 6

    def test_empty_inputs_raises(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, merge_pdfs

        with pytest.raises(PdfOpError, match="列表为空"):
            merge_pdfs([], tmp_path / "x.pdf")

    def test_missing_input_raises(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, merge_pdfs

        with pytest.raises(PdfOpError, match="不存在"):
            merge_pdfs([tmp_path / "nope.pdf"], tmp_path / "out.pdf")

    def test_out_path_parent_auto_mkdir(self, tmp_path: Path) -> None:
        """父目录不存在自动创建（atomic_writer 行为）。"""
        from civ_core.infra_io.pdf_io import merge_pdfs

        a = _make_test_pdf(tmp_path / "a.pdf", n_pages=2)
        out = tmp_path / "sub" / "deep" / "out.pdf"
        merge_pdfs([a], out)
        assert out.is_file()


# ──────────────────────────────────────────────────────────────────
# split_pdf_per_page
# ──────────────────────────────────────────────────────────────────
class TestSplitPerPage:
    def test_basic_split(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import split_pdf_per_page

        src = _make_test_pdf(tmp_path / "report.pdf", n_pages=3)
        out_dir = tmp_path / "out"
        written = split_pdf_per_page(src, out_dir)

        assert len(written) == 3
        for p in written:
            assert p.is_file()
            r = PdfReader(str(p))
            assert len(r.pages) == 1

    def test_filename_zero_padded(self, tmp_path: Path) -> None:
        """12 页 → p01..p12（2 位 padding，保持字典序）。"""
        from civ_core.infra_io.pdf_io import split_pdf_per_page

        src = _make_test_pdf(tmp_path / "doc.pdf", n_pages=12)
        out_dir = tmp_path / "out"
        written = split_pdf_per_page(src, out_dir)
        names = [p.name for p in written]
        assert names[0] == "doc_p01.pdf"
        assert names[-1] == "doc_p12.pdf"

    def test_custom_template(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import split_pdf_per_page

        src = _make_test_pdf(tmp_path / "x.pdf", n_pages=2)
        out_dir = tmp_path / "out"
        written = split_pdf_per_page(src, out_dir, name_template="page-{n}-of-{stem}.pdf")
        # 名字应是 page-01-of-x.pdf
        assert written[0].name.startswith("page-01-of-x")

    def test_missing_input_raises(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, split_pdf_per_page

        with pytest.raises(PdfOpError, match="不存在"):
            split_pdf_per_page(tmp_path / "nope.pdf", tmp_path)


# ──────────────────────────────────────────────────────────────────
# split_pdf_by_ranges
# ──────────────────────────────────────────────────────────────────
class TestSplitByRanges:
    def test_single_range(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import split_pdf_by_ranges

        src = _make_test_pdf(tmp_path / "doc.pdf", n_pages=10)
        out_dir = tmp_path / "out"
        written = split_pdf_by_ranges(src, out_dir, "1-3")
        assert len(written) == 1
        r = PdfReader(str(written[0]))
        assert len(r.pages) == 3

    def test_multiple_ranges_and_single_pages(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import split_pdf_by_ranges

        src = _make_test_pdf(tmp_path / "doc.pdf", n_pages=10)
        out_dir = tmp_path / "out"
        written = split_pdf_by_ranges(src, out_dir, "1-3,5,7-9")
        assert len(written) == 3
        # 文件名校验
        names = sorted(p.name for p in written)
        assert names == sorted(["doc_1-3.pdf", "doc_5-5.pdf", "doc_7-9.pdf"])

    def test_invalid_expr_propagates(self, tmp_path: Path) -> None:
        from civ_core.infra_io.pdf_io import PdfOpError, split_pdf_by_ranges

        src = _make_test_pdf(tmp_path / "doc.pdf", n_pages=10)
        with pytest.raises(PdfOpError):
            split_pdf_by_ranges(src, tmp_path / "out", "1-99")  # 超界
