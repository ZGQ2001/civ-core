"""
照片流水线工具 —— 一键完成"按缺陷清单排序 → 题注重编号"两步操作。

等价于手动依次运行 sort_photos.py 和 renumber_photos.py，
但只需配置一次参数、中间临时文件自动清理。
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

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
from renumber_photos import run_renumber
from sort_photos import run_sort
from ui_components import ModernDynamicFormDialog, ModernInfoDialog


# ==========================================
# 模块 1：核心业务（可被其他工具复用）
# ==========================================
def run_pipeline(
    excel_path: str,
    sheet_name: str | None,
    col_name: str,
    word_path: str,
    output_word_path: str,
    output_excel_path: str,
) -> None:
    """排序 → 重编号两步串联流水线。

    中间产物（已排序但尚未重编号的 Word）写到 output_word_path 同目录的临时文件，
    流水线结束后自动删除。
    """
    output_dir = os.path.dirname(output_word_path)
    base_name = os.path.splitext(os.path.basename(output_word_path))[0]
    temp_path = os.path.join(output_dir, f"_temp_sorted_{base_name}.docx")

    print("=" * 60)
    print("▶ 阶段 1 / 2：照片排序")
    print("=" * 60)
    run_sort(
        excel_path=excel_path,
        sheet_name=sheet_name,
        col_name=col_name,
        word_path=word_path,
        output_path=temp_path,
    )

    if not os.path.exists(temp_path):
        print("❌ 排序阶段未生成输出文件，流水线中止。")
        return

    print()
    print("=" * 60)
    print("▶ 阶段 2 / 2：题注重编号")
    print("=" * 60)
    try:
        run_renumber(
            excel_path=excel_path,
            sheet_name=sheet_name,
            col_name=col_name,
            word_path=temp_path,
            output_word_path=output_word_path,
            output_excel_path=output_excel_path,
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print(f"🗑  已清理临时文件: {os.path.basename(temp_path)}")

    print()
    print("🎉 流水线全部完成！")
    print(f"   📄 最终 Word : {output_word_path}")
    print(f"   📊 最终 Excel: {output_excel_path}")


# ==========================================
# 模块 2：UI 流程
# ==========================================
def _request_params(excel_path: str, sheet_names: list[str]) -> dict | None:
    default_dir = os.path.dirname(excel_path) or os.getcwd()
    schema = [
        field_sheet_select(sheet_names),
        field_text("excel_col", "照片列表头:", default="照片"),
        field_word_file(label="原始 Word（待排序）:", default="待排序_附录1.docx"),
        field_dir(default=default_dir),
        field_text("output_word_name", "输出 Word 文件名:", default="已完成_附录1.docx"),
        field_text("output_excel_name", "输出 Excel 文件名:", default="已完成_缺陷清单.xlsx"),
    ]
    return ModernDynamicFormDialog(
        title="照片流水线（排序 + 重编号）- 参数配置",
        form_schema=schema,
        width=640,
    ).show()


def _main() -> None:
    enable_line_buffered_stdout()

    excel_path = pick_excel_file(title="第一步：选择缺陷清单 Excel")
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
        params.get("output_word_name") or "已完成_附录1.docx", (".docx",)
    )
    output_excel = ensure_extension(
        params.get("output_excel_name") or "已完成_缺陷清单.xlsx",
        (".xlsx", ".xlsm"),
        default=".xlsx",
    )

    try:
        run_pipeline(
            excel_path=excel_path,
            sheet_name=params.get("sheet_name") or sheets[0],
            col_name=params.get("excel_col") or "照片",
            word_path=word_path,
            output_word_path=os.path.join(output_dir, output_word),
            output_excel_path=os.path.join(output_dir, output_excel),
        )
        ModernInfoDialog(
            "流水线完成",
            f"✅ 排序 + 重编号全部完成！\n\n📄 Word: {output_word}\n📊 Excel: {output_excel}",
        ).show()
    except Exception as e:
        ModernInfoDialog("流水线异常", f"❌ 执行过程中出错:\n\n{e}").show()
        raise


if __name__ == "__main__":
    _main()
