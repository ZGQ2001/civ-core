"""pdf_tools handlers：PDF 合并/拆分 RPC 接口。

RPC 方法（前缀 "pdf_tools."）：
  pdf_tools.merge(inputs, output)
    -> {output: str, count: int}
  pdf_tools.split_per_page(input, output_dir, name_template="{stem}_p{n}.pdf")
    -> {written: [str], count: int}
  pdf_tools.split_by_ranges(input, output_dir, expr, name_template="{stem}_{start}-{end}.pdf")
    -> {written: [str], count: int}
"""

from __future__ import annotations

from pathlib import Path

from civ_core.infra_io.pdf_io import (
    merge_pdfs,
    split_pdf_by_ranges,
    split_pdf_per_page,
)

__all__ = ["merge", "split_per_page", "split_by_ranges"]


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
    written = split_pdf_by_ranges(
        Path(input), Path(output_dir), expr, name_template=name_template
    )
    return {"written": [str(p) for p in written], "count": len(written)}
