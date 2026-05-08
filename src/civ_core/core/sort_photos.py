"""
照片排序工具 —— 按 Excel 缺陷清单的顺序重排已排序 Word 附录里的照片。

业务逻辑由 common/ 提供的纯函数完成；本文件只负责：
    - 调度（run_sort）
    - UI 流程（__main__ 入口）
"""

import os
import sys

# 确保以"脚本"方式被 main.py / 终端启动时也能找到 common/
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import pythoncom
import win32com.client
from common.excel_helpers import get_excel_sort_order
from common.io_helpers import (
    enable_line_buffered_stdout,
    ensure_extension,
    kill_winword_processes,
    pick_excel_file,
    read_sheet_names,
    unblock_file,
)
from common.types import PhotoPair
from common.ui_helpers import (
    field_dir,
    field_sheet_select,
    field_text,
    field_word_file,
)
from common.word_helpers import scan_photo_pairs
from ui_components import ModernDynamicFormDialog


# ==========================================
# 模块 1：核心业务（纯参数，不依赖 UI / 全局态，可被其他工具复用）
# ==========================================
def rebuild_word_by_order(
    src_doc_path: str,
    output_path: str,
    pairs: dict[int, PhotoPair],
    unmatched: list[PhotoPair],
    excel_order: list[int],
) -> None:
    """通过 Word COM 重建文档：按 excel_order 排好图 + 题注，保留图片。

    pairs: {图号: 该配对在源表中的位置}
    unmatched: 源表里有但 Excel 没排序的配对（追加到末尾）
    """
    kill_winword_processes(reason="启动 Word COM 前预清理")
    unblock_file(src_doc_path)

    pythoncom.CoInitialize()
    word_app = None
    try:
        print("📋 启动 Word 应用 (DispatchEx 强制新进程)...")
        word_app = win32com.client.DispatchEx("Word.Application")
        word_app.Visible = True  # 调试期间可见；问题定位后改回 False
        word_app.DisplayAlerts = 0
        try:
            word_app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass

        print("📂 打开源文档...")
        src_doc = word_app.Documents.Open(
            FileName=os.path.abspath(src_doc_path),
            ConfirmConversions=False,
            ReadOnly=False,
            AddToRecentFiles=False,
            Revert=False,
            Format=0,
            Visible=True,
            OpenAndRepair=False,
            NoEncodingDialog=True,
        )
        print("✅ 源文档已打开")

        new_doc = word_app.Documents.Add()
        if new_doc.Tables.Count > 0:
            new_doc.Tables(1).Delete()

        src_table = src_doc.Tables(1)
        src_cols = src_table.Columns.Count
        print(f"📊 源表格 {src_table.Rows.Count} 行 × {src_cols} 列")

        # 拼最终顺序：Excel 顺序里能匹配的优先，剩下的追加
        final_list: list[PhotoPair] = [pairs[n] for n in excel_order if n in pairs]
        final_list.extend(unmatched)
        print(f"📋 共 {len(final_list)} 个配对待重排")

        # 还原"上图下注、每行 src_cols 张图"的版式
        pairs_per_group = src_cols
        num_groups = (len(final_list) + pairs_per_group - 1) // pairs_per_group
        total_new_rows = num_groups * 2

        print(f"🔨 创建新表格 ({total_new_rows} 行 × {src_cols} 列)...")
        new_table = new_doc.Tables.Add(
            Range=new_doc.Range(0, 0),
            NumRows=total_new_rows,
            NumColumns=src_cols,
            DefaultTableBehavior=1,  # wdWord9TableBehavior
        )
        new_table.Borders.Enable = True

        for idx, item in enumerate(final_list):
            if idx % 10 == 0:
                print(f"🔄 进度: {idx + 1}/{len(final_list)}")

            group_idx = idx // pairs_per_group
            col_in_new = (idx % pairs_per_group) + 1
            img_row = group_idx * 2 + 1
            txt_row = group_idx * 2 + 2

            _copy_cell(
                src_table,
                item.img_row_idx + 1,
                item.img_col_idx + 1,
                new_table,
                img_row,
                col_in_new,
                fallback_text="[图片]",
                tag=f"图片[{idx}]",
            )
            _copy_cell(
                src_table,
                item.txt_row_idx + 1,
                item.txt_col_idx + 1,
                new_table,
                txt_row,
                col_in_new,
                fallback_text=None,
                tag=f"文字[{idx}]",
            )

        print("💾 保存新文档...")
        new_doc.SaveAs(os.path.abspath(output_path))
        new_doc.Close()
        src_doc.Close()
        print(f"✅ 完成！输出文件: {output_path}")

    except Exception as e:
        print(f"❌ COM 重构失败: {e}")
        raise
    finally:
        if word_app:
            try:
                word_app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        kill_winword_processes(reason="退出兜底")


def _copy_cell(
    src_table,
    src_row: int,
    src_col: int,
    dst_table,
    dst_row: int,
    dst_col: int,
    fallback_text: str | None,
    tag: str,
) -> None:
    """COM 单元格拷贝；失败时设兜底文本。"""
    src_cell = src_table.Cell(Row=src_row, Column=src_col)
    dst_cell = dst_table.Cell(Row=dst_row, Column=dst_col)
    try:
        src_cell.Range.Copy()
        dst_cell.Range.Paste()
    except Exception as e:
        print(f"⚠️ 复制单元格 {tag} 失败: {e}")
        dst_cell.Range.Text = fallback_text if fallback_text is not None else src_cell.Range.Text


def run_sort(
    excel_path: str, sheet_name: str | None, col_name: str, word_path: str, output_path: str
) -> None:
    """工具入口：组合"读 Excel 顺序 → 扫 Word 表格 → COM 重建"。

    被 __main__ 调用，也可被其他脚本（比如 batch / pipeline 工具）直接 import 调用。
    """
    print(f"🚀 读取排序数据... [Sheet: {sheet_name}]")
    order = get_excel_sort_order(excel_path, col_name, sheet_name)
    if not order:
        print("⚠️ 终止：Excel 排序数据为空。")
        return

    print(f"📊 从 Excel 获取到 {len(order)} 个排序指令")
    print("—— 阶段 A：解析 Word 表格 ——")
    pairs, unmatched = scan_photo_pairs(word_path, valid_nums=set(order))

    print("—— 阶段 B：通过 Word COM 重构文档 ——")
    rebuild_word_by_order(word_path, output_path, pairs, unmatched, order)


# ==========================================
# 模块 2：UI 流程（独立脚本入口）
# ==========================================
def _request_params(excel_path: str, sheet_names: list[str]) -> dict | None:
    default_dir = os.path.dirname(excel_path) or os.getcwd()
    schema = [
        field_sheet_select(sheet_names),
        field_text("excel_col", "照片列表头:", default="照片"),
        field_word_file(label="待排序 Word:", default="待排序_附录1.docx"),
        field_dir(default=default_dir),
        field_text("output_name", "输出文件名:", default="已排序_附录1.docx"),
    ]
    return ModernDynamicFormDialog(
        title="照片排序 - 参数配置", form_schema=schema, width=620
    ).show()


def _main():
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
    output_name = ensure_extension(params.get("output_name") or "已排序_附录1.docx", (".docx",))
    output_path = os.path.join(output_dir, output_name)

    run_sort(
        excel_path=excel_path,
        sheet_name=params.get("sheet_name") or sheets[0],
        col_name=params.get("excel_col") or "照片",
        word_path=word_path,
        output_path=output_path,
    )


if __name__ == "__main__":
    _main()
