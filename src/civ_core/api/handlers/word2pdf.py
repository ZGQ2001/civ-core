"""word2pdf handlers：Word → PDF 批量转换 RPC 接口。

RPC 方法（前缀 "word2pdf."）：
  word2pdf.convert(inputs, output_dir)
    -> {written: [str], failed: [{path, error}], total: int}
  word2pdf.inspect(paths)
    -> {files: [{path, size_kb, paragraphs, pages?, error?}]}
       给前端「中间预览」用：列每个 docx 的体量信息。
       - paragraphs: 段落数（python-docx 数）；可作为「文档大小」粗略指标
       - pages: docProps/app.xml 缓存的页数（Word 真正打开保存过才有）；
         缺失就只显示段落数

未来 T5.5 起手 C# sidecar 后，docx 的解析（含 Word 模板填充）会切到
OpenXML SDK 原生 —— 那时 inspect 也会有更准的页数估计。当前 Python
端给 UI 一个最小可用的预览即可。
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from civ_core.infra_io.word_to_pdf import convert_batch

__all__ = ["convert", "inspect"]


def convert(inputs: list[str], output_dir: str) -> dict:
    result = convert_batch([Path(p) for p in inputs], Path(output_dir))
    return {
        "written": [str(p) for p in result.written],
        "failed": [
            {"path": str(src), "error": f"{type(e).__name__}: {e}"} for src, e in result.failed
        ],
        "total": len(inputs),
    }


def inspect(paths: list[str]) -> dict:
    """读每个 docx 的文件大小 + 段落数 + 缓存页数（如可读）。

    单个文件失败 → files[i] 带 error 字段，不影响其他文件。docx 是 zip 包，
    docProps/app.xml 里 <Pages> 字段由 Word 真打开保存时缓存；纯 python-docx
    生成的或 docxtpl 写完后没在 Word 打开过的文件可能没这字段，UI 就只显示段落数。
    """
    files: list[dict] = []
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
            item["error"] = f"读文件大小失败：{e}"
            files.append(item)
            continue

        # 段落数：python-docx 直接拿
        try:
            from docx import Document

            doc = Document(str(path))
            item["paragraphs"] = len(doc.paragraphs)
        except Exception as e:
            # 走到这里通常是不是合法 docx / 加密 / 旧 .doc 格式
            item["error"] = f"解析失败：{type(e).__name__}: {e}"
            files.append(item)
            continue

        # 缓存页数（可选）：读 docProps/app.xml 里的 <Pages>
        pages = _read_cached_pages(path)
        if pages is not None:
            item["pages"] = pages

        files.append(item)
    return {"files": files}


def _read_cached_pages(path: Path) -> int | None:
    """从 docx 的 docProps/app.xml 读 <Pages> 缓存值。

    Word 真正打开保存时会写这个字段；纯 python-docx 生成的 docx 通常没有，
    返 None。命名空间是 extended-properties；遍历找以 }Pages 结尾的元素即可
    （避开手写命名空间常量带版本差）。
    """
    try:
        with zipfile.ZipFile(path) as zf:
            with zf.open("docProps/app.xml") as f:
                root = ET.parse(f).getroot()
        for el in root.iter():
            if el.tag.endswith("}Pages") or el.tag == "Pages":
                text = (el.text or "").strip()
                if text:
                    return int(text)
    except (KeyError, zipfile.BadZipFile, ET.ParseError, ValueError, OSError):
        return None
    return None
