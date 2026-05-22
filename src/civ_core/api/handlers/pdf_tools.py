"""pdf_tools handlers：PDF 合并/拆分 RPC 接口。

RPC 方法（前缀 "pdf_tools."）：
  pdf_tools.merge(inputs, output)
    -> {output: str, count: int}
  pdf_tools.split_per_page(input, output_dir, name_template="{stem}_p{n}.pdf")
    -> {written: [str], count: int}
  pdf_tools.split_by_ranges(input, output_dir, expr, name_template="{stem}_{start}-{end}.pdf")
    -> {written: [str], count: int}
  pdf_tools.inspect(paths)
    -> {files: [{path, pages, size_kb, error?}], total_pages: int}
       给前端「中间预览」用：列出每个 PDF 的页数 + 大小，单个失败不影响整体。
"""

from __future__ import annotations

from pathlib import Path

from civ_core.infra_io.pdf_io import (
    merge_pdfs,
    split_pdf_by_ranges,
    split_pdf_per_page,
)

__all__ = ["merge", "split_per_page", "split_by_ranges", "inspect"]


def merge(inputs: list[str], output: str) -> dict:
    """按 inputs 顺序合并为单个 PDF。"""
    out = merge_pdfs([Path(p) for p in inputs], Path(output))
    return {"output": str(out), "count": len(inputs)}


def split_per_page(
    input: str,  # noqa: A002 — RPC 接口键固定为 "input"
    output_dir: str,
    name_template: str = "{stem}_p{n}.pdf",
) -> dict:
    written = split_pdf_per_page(Path(input), Path(output_dir), name_template=name_template)
    return {"written": [str(p) for p in written], "count": len(written)}


def split_by_ranges(
    input: str,  # noqa: A002
    output_dir: str,
    expr: str,
    name_template: str = "{stem}_{start}-{end}.pdf",
) -> dict:
    written = split_pdf_by_ranges(Path(input), Path(output_dir), expr, name_template=name_template)
    return {"written": [str(p) for p in written], "count": len(written)}


def inspect(paths: list[str]) -> dict:
    """读每个 PDF 的页数 + 文件大小给前端预览（合并模式列表 / 拆分模式单文件信息）。

    单个文件失败（路径错 / 加密 / 损坏）→ files[i] 带 error 字段，不影响其他文件
    和合计逻辑。total_pages 只累加 pages 不为 None 的项。
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    files: list[dict] = []
    total = 0
    for p in paths:
        path = Path(p)
        item: dict = {"path": p}
        if not path.is_file():
            item["error"] = f"文件不存在：{p}"
            files.append(item)
            continue
        try:
            item["size_kb"] = round(path.stat().st_size / 1024, 1)
        except OSError as e:
            item["size_kb"] = None
            item["error"] = f"读文件大小失败：{e}"
            files.append(item)
            continue
        try:
            reader = PdfReader(str(path))
            n = len(reader.pages)
            item["pages"] = n
            total += n
        except (PdfReadError, ValueError, OSError) as e:
            item["error"] = f"解析失败：{type(e).__name__}: {e}"
        files.append(item)
    return {"files": files, "total_pages": total}
