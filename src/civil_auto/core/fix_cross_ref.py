r"""
===============================================================================
脚本名称：修复交叉引用格式 (fix_cross_ref.py)
作者: ZGQ
功能概述：
    本脚本用于自动化处理 Word/WPS 检测报告中的交叉引用格式，
    解决手动调整耗时且易漏项的问题，保证每次的格式一致性。

核心工作流：
    1. 环境检测：抓取当前处于激活状态的 Word/WPS 文档并死锁内存对象。
    2. 触发静默克隆备份。
    3. 遍历所有域代码, 定位交叉引用 (REF 域) 。
    4. 检查每个交叉引用是否已包含保留格式的开关 (\* MERGEFORMAT) 。
    5. 对于缺失该开关的交叉引用，自动追加 \* MERGEFORMAT 开关以确保格式稳定。
===============================================================================
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import win32com.client
from common.file_utils import backup_current_document
from ui_components import ModernConfirmDialog, ModernInfoDialog


def update_cross_references(app, target_doc):
    """
    修复锁定文档中的交叉引用格式。
    """
    doc_name = target_doc.Name

    # 1. 启动确认与防呆
    dialog = ModernConfirmDialog(
        title="交叉引用修复引擎启动",
        message=f"当前文件：{doc_name}",
        sub_message="是否为所有交叉引用追加保留格式开关 (\\* MERGEFORMAT) ？\n\n确认后将调用静默备份并开始执行。",
    )
    if not dialog.show():
        return False

    # 2. 执行统一静默备份
    print("正在调用外部模块进行静默备份...")
    if not backup_current_document(target_doc):
        ModernInfoDialog("安全熔断", "⚠️ 备份模块返回失败信号！操作已终止。").show()
        return False

    try:
        # 关闭屏幕更新以提高处理速度
        app.ScreenUpdating = False

        # 3. 锁定死锁的文档对象进行遍历
        fields = target_doc.Fields
        count = 0

        for i in range(1, fields.Count + 1):
            f = fields.Item(i)
            # 3代表wdFieldRef，即交叉引用/引用域
            if f.Type == 3:
                code_text = f.Code.Text
                # 检查是否已经存在格式保护开关
                if "\\* MERGEFORMAT" not in code_text.upper():
                    f.Code.Text = code_text + " \\* MERGEFORMAT"
                    count += 1

        # 4. 成功反馈
        ModernInfoDialog(
            "执行完毕", f"✅ 交叉引用修复完毕！\n\n共为 {count} 个交叉引用追加了保留格式开关。"
        ).show()
        return True

    except Exception as e:
        ModernInfoDialog("运行期错误", f"执行过程中出错:\n{e}").show()
        return False

    finally:
        app.ScreenUpdating = True


if __name__ == "__main__":
    try:
        app = win32com.client.GetActiveObject("Word.Application")
    except:
        try:
            app = win32com.client.GetActiveObject("KWPS.Application")
        except:
            app = None

    if not app:
        ModernInfoDialog(
            "运行阻断", "未检测到运行中的 WPS 或 Word 程序。\n\n请先打开需要修复的报告文档！"
        ).show()
    else:
        # 隐患拦截：防止未保存的新建文档导致备份异常
        if app.ActiveDocument.Path == "":
            ModernInfoDialog(
                "操作阻断",
                "该文档尚未保存到本地硬盘。\n请先手动保存一次（Ctrl+S）后再执行修复程序！",
            ).show()
        else:
            # 【核心护城河】：获取目标文档并死锁内存指针，贯穿全局
            target_doc = app.ActiveDocument
            update_cross_references(app, target_doc)
