"""
照片重编号工具 —— sort_photos.py 的下游配套。

业务逻辑全部在 common/ 里，本文件只负责调度（run_renumber）+ UI 流程（__main__）。
"""

import os
import sys

# 让脚本方式启动时也能找到 common/
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.excel_helpers import replace_in_excel_column
from common.io_helpers import (
    enable_line_buffered_stdout,
    ensure_extension,
    pick_excel_file,
    read_sheet_names,
)
from common.ui_helpers import (
    field_dir,
    field_sheet_select,
    field_text,
    field_word_file,
)
from common.word_helpers import build_caption_renumber_mapping, replace_in_caption_rows
from ui_components import ModernDynamicFormDialog


# ==========================================
# 模块 1：核心业务（可被其他工具复用）
# ==========================================
def run_renumber(
    excel_path: str,
    sheet_name: str | None,
    col_name: str,
    word_path: str,
    output_word_path: str,
    output_excel_path: str,
) -> None:
    """工具入口：扫 Word 建映射 → 改 Word 题注 → 改 Excel 引用。"""
    print("—— 阶段 A：扫描 Word 构建编号映射 ——")
    mapping = build_caption_renumber_mapping(word_path)
    if not mapping:
        print("⚠️ 终止：未在 Word 题注中检测到任何'图 N'。")
        return

    print("—— 阶段 B：改写 Word 题注 ——")
    run_count, fallback_count, word_unmatched = replace_in_caption_rows(
        word_path,
        mapping,
        output_word_path,
    )
    print(f"   ↳ run 级替换 {run_count} 处，段落级回退 {fallback_count} 处")
    if word_unmatched:
        uniq = sorted(set(word_unmatched))
        print(f"   ⚠️ Word 中 {len(uniq)} 个编号无映射: {uniq[:10]}{' …' if len(uniq) > 10 else ''}")

    print("—— 阶段 C：同步改写 Excel 引用 ——")
    replaced, excel_unmatched = replace_in_excel_column(
        excel_path,
        sheet_name,
        col_name,
        mapping,
        output_excel_path,
    )
    print(f"   ↳ 已更新 {replaced} 个单元格")
    if excel_unmatched:
        uniq = sorted(set(excel_unmatched))
        print(
            f"   ⚠️ Excel 中 {len(uniq)} 个编号无映射: {uniq[:10]}{' …' if len(uniq) > 10 else ''}"
        )

    print("\n🎉 全部完成！")
    print(f"   📄 Word: {output_word_path}")
    print(f"   📊 Excel: {output_excel_path}")


# ==========================================
# 模块 2：UI 流程
# ==========================================
def _request_params(excel_path: str, sheet_names: list[str]) -> dict | None:
    default_dir = os.path.dirname(excel_path) or os.getcwd()
    schema = [
        field_sheet_select(sheet_names),
        field_text("excel_col", "照片列表头:", default="照片"),
        field_word_file(label="已排序的 Word:", default="已排序_附录1.docx"),
        field_dir(default=default_dir),
        field_text("output_word_name", "输出 Word 文件名:", default="已重编号_附录1.docx"),
        field_text("output_excel_name", "输出 Excel 文件名:", default="已重编号_缺陷清单.xlsx"),
    ]
    return ModernDynamicFormDialog(
        title="照片重编号 - 参数配置", form_schema=schema, width=620
    ).show()


def _main():
    enable_line_buffered_stdout()

    excel_path = pick_excel_file(title="第一步：选择已排序的缺陷清单 Excel")
    if not excel_path:
        print("⚠️ 已取消：未选择 Excel 文件。")
        return

    sheets = read_sheet_names(excel_path)
    if not sheets:
        print("⚠️ 终止：该 Excel 没有可读取的工作表。")
        return

    params = _request_params(excel_path, sheets)
    if not params or not params.get("word_path"):
        print("⚠️ 已取消：未选择 Word 文件或直接关闭了窗口。")
        return

    word_path = params["word_path"]
    output_dir = params.get("output_dir") or os.path.dirname(word_path)
    output_word = ensure_extension(
        params.get("output_word_name") or "已重编号_附录1.docx", (".docx",)
    )
    output_excel = ensure_extension(
        params.get("output_excel_name") or "已重编号_缺陷清单.xlsx",
        (".xlsx", ".xlsm"),
        default=".xlsx",
    )

    run_renumber(
        excel_path=excel_path,
        sheet_name=params.get("sheet_name") or sheets[0],
        col_name=params.get("excel_col") or "照片",
        word_path=word_path,
        output_word_path=os.path.join(output_dir, output_word),
        output_excel_path=os.path.join(output_dir, output_excel),
    )


if __name__ == "__main__":
    _main()
