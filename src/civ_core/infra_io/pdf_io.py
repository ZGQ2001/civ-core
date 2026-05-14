"""PDF 合并 / 拆分的 IO 层（基于 pypdf）。

为什么独立成模块：
  • core/ 不允许直接 IO（CLAUDE.md 总纲），pypdf 读写都属于 IO
  • 落盘走 atomic_writer：避免合并到一半被占用产生半截 PDF
  • 解析"1-3,5,7-9"页号范围表达式有正则 + 边界校验，单独抽出便于纯函数单测

对外 API：
  parse_page_ranges(expr, total_pages)            纯函数：解析页号表达式 → [(start, end)]
  merge_pdfs(inputs, out_path)                    顺序合并 → 1 个 PDF
  split_pdf_per_page(in_path, out_dir, *, ...)    每页 1 个 PDF
  split_pdf_by_ranges(in_path, out_dir, ranges)   每范围 1 个 PDF（保留页内顺序）

错误约定（与 chart_writer / file_manager 一致）：
  PdfOpError —— 业务级错误带 hint；UI 三段式提示直接消费
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from civ_core.infra_io.file_manager import (
    FileBusyError,
    FileWriteError,
    atomic_writer,
)
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────────────────────────
class PdfOpError(RuntimeError):
    """PDF 操作业务异常。hint 字段供 UI 三段式提示用。"""

    hint: str

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


# ──────────────────────────────────────────────────────────────────
# 页号表达式解析（纯函数）
# ──────────────────────────────────────────────────────────────────
# 匹配单页 ("3") 或范围 ("1-5")；空白容忍但末尾不允许 trailing
_TOKEN_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def parse_page_ranges(expr: str, total_pages: int) -> list[tuple[int, int]]:
    """解析 "1-3,5,7-9" 类页号表达式 → 0-based 半开区间 [(start, end), ...]。

    输入：1-based 页号（用户视角，PDF 阅读器都从 1 开始）
    输出：每段一对 (start_idx, end_idx) —— end 为半开（pypdf 切片用），
          即 1-3 ↦ (0, 3) 表示页 1、2、3

    校验：
      • 页号必须 >= 1 且 <= total_pages
      • 区间 "a-b" 必须 a <= b
      • 整个表达式不为空（用户至少填一段）
      • 不允许 "1-2-3" / "abc" / 空逗号项
    """
    if total_pages <= 0:
        raise PdfOpError("PDF 没有任何页可供拆分", hint="请确认输入 PDF 至少 1 页。")
    if not expr or not expr.strip():
        raise PdfOpError(
            "页号表达式不能为空",
            hint='填写示例："1-3,5,7-9" 代表三段：1~3 页、第 5 页、7~9 页',
        )

    ranges: list[tuple[int, int]] = []
    for raw in expr.split(","):
        token = raw.strip()
        if not token:
            raise PdfOpError(
                f"页号表达式中有空项（多余逗号？）：{expr!r}",
                hint="检查是否多打了逗号。",
            )
        m = _TOKEN_RE.match(token)
        if not m:
            raise PdfOpError(
                f"无法解析的页号片段：{token!r}",
                hint='合法格式：单页 "5" 或 范围 "1-3"；多段用逗号分隔。',
            )
        start_s, end_s = m.group(1), m.group(2)
        start = int(start_s)
        end = int(end_s) if end_s is not None else start
        if start < 1 or end < 1:
            raise PdfOpError(
                f"页号必须 >= 1，得到 {token!r}",
                hint="PDF 页号从 1 开始。",
            )
        if start > total_pages or end > total_pages:
            raise PdfOpError(
                f"页号超过 PDF 总页数 {total_pages}：{token!r}",
                hint=f"该 PDF 只有 {total_pages} 页。",
            )
        if start > end:
            raise PdfOpError(
                f"范围起止颠倒（{start} > {end}）：{token!r}",
                hint="范围必须是「小-大」，如 1-3。",
            )
        # 转 0-based 半开
        ranges.append((start - 1, end))
    return ranges


# ──────────────────────────────────────────────────────────────────
# 合并
# ──────────────────────────────────────────────────────────────────
def merge_pdfs(inputs: list[Path | str], out_path: Path | str) -> Path:
    """按 inputs 顺序合并为 1 个 PDF，落盘到 out_path（原子写）。

    参数：
      inputs    输入 PDF 列表（顺序即合并顺序）
      out_path  目标 PDF 路径；不存在会自动 mkdir parent

    返回写入成功的目标路径。

    异常：
      PdfOpError       inputs 为空 / 单个文件无法打开（损坏的 PDF）
      FileBusyError    out_path 被占用（atomic_writer 抛出）
      FileWriteError   父目录不可写 / 磁盘满
    """
    if not inputs:
        raise PdfOpError("合并列表为空", hint="请至少加入 1 个 PDF（建议 ≥ 2 才有意义）。")

    out = Path(out_path)
    writer = PdfWriter()
    try:
        for raw in inputs:
            p = Path(raw)
            if not p.is_file():
                raise PdfOpError(
                    f"输入文件不存在：{p}",
                    hint="请检查路径，或重新选择文件。",
                )
            try:
                writer.append(str(p))
            except Exception as e:
                raise PdfOpError(
                    f"无法读取 {p.name}：{e}",
                    hint="该 PDF 可能损坏或被加密；请用阅读器打开试试。",
                ) from e

        # 落盘走 atomic_writer：失败不留半截文件
        with atomic_writer(out) as tmp:
            with tmp.open("wb") as fh:
                writer.write(fh)
    finally:
        writer.close()

    log.info("PDF 合并完成：%d 个 → %s", len(inputs), out)
    return out


# ──────────────────────────────────────────────────────────────────
# 拆分：每页 1 个
# ──────────────────────────────────────────────────────────────────
def split_pdf_per_page(
    in_path: Path | str,
    out_dir: Path | str,
    *,
    name_template: str = "{stem}_p{n}.pdf",
) -> list[Path]:
    """把 PDF 每一页拆成单独的 PDF 文件。

    name_template 占位符：
      {stem}  输入 PDF 文件名去后缀（如 report.pdf → report）
      {n}     1-based 页号（自动 0 padding 到与总页数对齐位数）
    例如 5 页的 report.pdf → report_p1.pdf ... report_p5.pdf
    （注：n 占位会按总页数零填充：12 页 → p01..p12）

    返回写入成功的输出路径列表（顺序与原 PDF 页序一致）。
    """
    src = Path(in_path)
    if not src.is_file():
        raise PdfOpError(
            f"输入 PDF 不存在：{src}",
            hint="请检查路径或重新选择文件。",
        )
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(src))
    except Exception as e:
        raise PdfOpError(
            f"无法打开 {src.name}：{e}",
            hint="该 PDF 可能损坏或加密。",
        ) from e

    total = len(reader.pages)
    if total == 0:
        raise PdfOpError(f"{src.name} 没有任何页", hint="该 PDF 是空白文件，无法拆分。")
    width = max(2, len(str(total)))  # 至少 2 位（p01..p99）；超 99 用 3 位

    written: list[Path] = []
    for idx in range(total):
        n_str = str(idx + 1).zfill(width)
        out_name = name_template.format(stem=src.stem, n=n_str)
        out_path = out_dir_p / out_name

        writer = PdfWriter()
        try:
            writer.add_page(reader.pages[idx])
            with atomic_writer(out_path) as tmp:
                with tmp.open("wb") as fh:
                    writer.write(fh)
        finally:
            writer.close()
        written.append(out_path)

    log.info("PDF 拆分（每页）完成：%s → %d 个文件", src.name, total)
    return written


# ──────────────────────────────────────────────────────────────────
# 拆分：按页号范围
# ──────────────────────────────────────────────────────────────────
def split_pdf_by_ranges(
    in_path: Path | str,
    out_dir: Path | str,
    expr: str,
    *,
    name_template: str = "{stem}_{start}-{end}.pdf",
) -> list[Path]:
    """按 "1-3,5,7-9" 表达式拆分 PDF；每段输出 1 个 PDF。

    name_template 占位符：
      {stem}        输入 PDF stem
      {start} {end} 该段的 1-based 起止页号（包含两端）；单页时 start == end

    返回写入成功的输出路径列表。
    """
    src = Path(in_path)
    if not src.is_file():
        raise PdfOpError(
            f"输入 PDF 不存在：{src}",
            hint="请检查路径或重新选择文件。",
        )
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(src))
    except Exception as e:
        raise PdfOpError(
            f"无法打开 {src.name}:{e}",
            hint="该 PDF 可能损坏或加密。",
        ) from e

    total = len(reader.pages)
    ranges = parse_page_ranges(expr, total)

    written: list[Path] = []
    for start_idx, end_idx in ranges:
        # 反算回 1-based 的起止（end_idx 是半开 → end_1based = end_idx）
        start_1 = start_idx + 1
        end_1 = end_idx
        out_name = name_template.format(stem=src.stem, start=start_1, end=end_1)
        out_path = out_dir_p / out_name

        writer = PdfWriter()
        try:
            for i in range(start_idx, end_idx):
                writer.add_page(reader.pages[i])
            with atomic_writer(out_path) as tmp:
                with tmp.open("wb") as fh:
                    writer.write(fh)
        finally:
            writer.close()
        written.append(out_path)

    log.info(
        "PDF 拆分（范围 %s）完成：%s → %d 个文件",
        expr,
        src.name,
        len(written),
    )
    return written


__all__ = [
    "FileBusyError",
    "FileWriteError",
    "PdfOpError",
    "merge_pdfs",
    "parse_page_ranges",
    "split_pdf_by_ranges",
    "split_pdf_per_page",
]
