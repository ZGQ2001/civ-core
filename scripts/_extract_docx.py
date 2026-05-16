"""临时脚本：提取 docx 全文到 UTF-8 文本文件。"""
import sys

from docx import Document

sys.stdout.reconfigure(encoding='utf-8')

doc_path = r"C:\Users\张德帅\Desktop\工程规范标准\鉴定报告-小米智能制造产业基地项目（二局-报交车间）施工质量评价-0183.docx"
doc = Document(doc_path)

with open("data/output/_docx_full_text.txt", "w", encoding="utf-8") as f:
    for para in doc.paragraphs:
        f.write(para.text + "\n")
    f.write("\n\n========== 表格内容 ==========\n\n")
    for i, table in enumerate(doc.tables):
        f.write(f"\n--- 表格 {i+1} ---\n")
        for row in table.rows:
            row_text = []
            for cell in row.cells:
                row_text.append(cell.text)
            f.write(" | ".join(row_text) + "\n")

print("DONE: written to data/output/_docx_full_text.txt")
