"""批量提取多个 docx 全文到 UTF-8 文本文件，每份一个输出文件。"""
import sys
from pathlib import Path

from docx import Document

sys.stdout.reconfigure(encoding='utf-8')

# 4 份鉴定报告路径
doc_paths = [
    (r"D:\3JS\项目\鉴定\2026-1-1 小米\小米报告最终版_2026_05_12\鉴定报告-小米智能制造产业基地项目（二局-3号厂房）施工质量评价-0181.docx", "_0181"),
    (r"D:\3JS\项目\鉴定\2026-1-1 小米\小米报告最终版_2026_05_12\鉴定报告-小米智能制造产业基地项目（二局-报交车间）施工质量评价-0183.docx", "_0183"),
    (r"D:\3JS\项目\鉴定\2026-1-1 小米\小米报告最终版_2026_05_12\鉴定报告-小米智能制造产业基地项目施工质量评价（中汽-B号生产厂房）-0184.docx", "_0184"),
    (r"D:\3JS\项目\鉴定\2026-1-1 小米\小米报告最终版_2026_05_12\鉴定报告-小米智能制造产业基地项目施工质量评价（中汽-D号生产厂房）-0185.docx", "_0185"),
]

out_dir = Path("data/output")
out_dir.mkdir(parents=True, exist_ok=True)

for doc_path, suffix in doc_paths:
    out_file = out_dir / f"_docx_full_text{suffix}.txt"
    try:
        doc = Document(doc_path)
        with open(out_file, "w", encoding="utf-8") as f:
            for para in doc.paragraphs:
                f.write(para.text + "\n")
            f.write("\n\n========== 表格内容 ==========\n\n")
            for i, table in enumerate(doc.tables):
                f.write(f"\n--- 表格 {i+1} ---\n")
                for row in table.rows:
                    row_text = [cell.text for cell in row.cells]
                    f.write(" | ".join(row_text) + "\n")
        print(f"OK: {out_file}")
    except Exception as e:
        print(f"FAIL: {doc_path} -> {e}")

print("DONE")
