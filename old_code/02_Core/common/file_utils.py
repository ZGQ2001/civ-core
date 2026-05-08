"""通用文档/表格备份工具。

为传入的 Word/WPS 或 Excel/ET 内存对象提供安全备份功能。
通过 Application.Name 显式鉴别宿主类型，避免误用接口。
"""

import os
import time


def backup_current_document(target_obj) -> bool:
    """对 COM 文档对象做时间戳备份。返回是否成功。

    target_obj: Word.Document / Excel.Workbook 等 COM 对象。
    备份文件命名: 原名_backup_YYYYMMDD_HH时MM分.<ext>
    """
    try:
        try:
            doc_path = target_obj.Path
            doc_fullname = target_obj.FullName
            doc_name = target_obj.Name
        except Exception:
            doc_path = ""
            doc_fullname = ""
            doc_name = ""

        if not doc_path or doc_fullname == doc_name:
            print("【备份阻断】源文件尚未执行本地存储。")
            return False

        target_obj.Save()

        base, ext = os.path.splitext(doc_fullname)
        timestamp = time.strftime("%Y%m%d_%H时%M分")
        backup_path = f"{base}_backup_{timestamp}{ext}"

        app_name = ""
        try:
            app_name = target_obj.Application.Name
        except Exception:
            pass

        # Excel 系列：直接 SaveCopyAs
        if "Excel" in app_name or "表格" in app_name or "ET" in app_name:
            target_obj.SaveCopyAs(backup_path)
        else:
            # Word/WPS 系列：开新副本另存（避免改动 ActiveDocument 焦点）
            app = target_obj.Application
            backup_doc = app.Documents.Add(doc_fullname)
            backup_doc.SaveAs2(backup_path)
            backup_doc.Close(0)  # wdDoNotSaveChanges

        return True

    except Exception as e:
        # 兜底：把 COM 异常详情写到日志，便于事后排查
        error_log_path = os.path.join(os.path.dirname(__file__), "backup_error_log.txt")
        try:
            with open(error_log_path, "w", encoding="utf-8") as f:
                f.write(f"备份底层崩溃详情:\n{e!s}")
        except Exception:
            pass

        print(f"【备份异常】底层执行出错: {e}")
        return False
