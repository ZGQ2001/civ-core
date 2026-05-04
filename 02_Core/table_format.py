"""
===============================================================================
脚本名称：报告表格全量排版引擎 (table_format.py)
作者: ZGQ
功能概述：
    本脚本用于自动化处理 Word/WPS 检测报告中的表格及表名排版。
    V3.0 现代UI重构版：全面接入全局防吞窗 UI 组件库，加入时间限流防卡死机制。
===============================================================================
"""

import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import win32com.client
from common.file_utils import backup_current_document
from common.patterns import CELL_BLANK_NOISE_PATTERN, CELL_FULL_NOISE_PATTERN
from common.word_com import word_optimized_environment
from ui_components import (
    ModernConfirmDialog,
    ModernInfoDialog,
    ModernParamDialog,
    ModernProgressConsole,
)

# ---------------- 1. 配置与规则读取 ----------------


def load_style_config(report_type="检测报告"):
    config_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "04_Config", "report_style_config.json")
    )
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"【阻断】未找到配置文件：{config_path}")
    with open(config_path, encoding="utf-8") as f:
        full_config = json.load(f)
    if report_type not in full_config:
        raise ValueError(f"【阻断】配置文件中不存在该报告类型：{report_type}")
    return full_config[report_type]


class GlobalConfig:
    def __init__(self):
        self.report_type = "检测报告"
        self.table_width_percent = 100
        self.skip_pages = []
        self.empty_cell_color = 255


class AuditLog:
    def __init__(self):
        self.total = 0
        self.success = 0
        self.skipped = 0
        self.errors = 0
        self.empty_cells = []
        self.error_details = []


config = GlobalConfig()
audit_log = AuditLog()

# ---------------- 2. 交互模块 (UI) ----------------


def show_ui_and_get_params(file_name):
    """通过现代 UI 获取参数"""
    # 调用 ModernParamDialog，并开启宽度输入选项
    dialog = ModernParamDialog("表格排版参数设置", file_name, show_width=True)
    params = dialog.show()

    if params:
        # 将获取的参数写入全局配置
        config.report_type = params.get("report_type", "检测报告")
        config.skip_pages = params.get("skip_pages", [])
        config.table_width_percent = params.get("width", 100)
        return True
    return False


def final_check_summary(file_name):
    """显示最终确认摘要"""
    summary = (
        f"报告类型: {config.report_type}\n"
        f"表格宽度: {config.table_width_percent}%\n"
        f"跳过页码: {config.skip_pages if config.skip_pages else '无'}\n\n"
        "字体、字号及表名间距将自动从 JSON 配置库读取。\n"
        "确认执行后，将调用静默备份并开始排版。"
    )
    dialog = ModernConfirmDialog("请最终确认配置清单", f"目标文件: {file_name}", summary)
    return dialog.show()


# ---------------- 3. 核心引擎 (COM) ----------------


def process_all_tables(app, target_doc):
    """
    处理文档中的所有表格。
    """
    try:
        style_db = load_style_config(config.report_type)
        title_cfg = style_db.get(
            "图表名称",
            {
                "chinese_font": "宋体",
                "english_font": "Times New Roman",
                "font_size": 10.5,
                "alignment": 1,
                "space_before": 0.5,
                "space_after": 0,
            },
        )
        cell_cfg = style_db.get(
            "表格正文",
            {"chinese_font": "宋体", "english_font": "Times New Roman", "font_size": 10.5},
        )

        doc = target_doc
        tables = doc.Tables
        table_count = tables.Count
        audit_log.total = table_count
        if table_count == 0:
            return True

        # 调用现代进度条组件
        progress_ui = ModernProgressConsole("表格自动排版程序", table_count)

        with word_optimized_environment(app):
            max_skip = max(config.skip_pages) if config.skip_pages else 0
            passed_skip_zone = False
            last_ui_update = time.time()  # 初始化时间戳

            for idx in range(1, table_count + 1):
                tbl = tables.Item(idx)

                # 监听停止信号
                if progress_ui.is_cancelled:
                    print("【中断】用户手动终止了表格排版。")
                    break

                # 时间限流：按时间差控制 UI 刷新，防止阻塞主线程
                current_time = time.time()
                if current_time - last_ui_update >= 0.05 or idx == table_count:
                    progress_ui.update_progress(idx, f"正在排版: {idx}/{table_count} 表")
                    last_ui_update = current_time

                try:
                    # B. 跳过页码判定与越界断路
                    page_num = 999
                    if config.skip_pages and not passed_skip_zone:
                        try:
                            page_num = tbl.Range.Information(3)
                            if page_num > max_skip:
                                passed_skip_zone = True
                        except:
                            pass

                    if page_num != 999 and page_num in config.skip_pages:
                        audit_log.skipped += 1
                        continue

                    # A. 表名判定与 JSON 规则下发
                    try:
                        title_range = tbl.Range.Previous(4, 1)
                        if title_range and CELL_BLANK_NOISE_PATTERN.sub(
                            "", title_range.Text
                        ).startswith("表"):
                            tf = title_range.Font
                            eng_font = title_cfg["english_font"]
                            tf.Name = eng_font
                            tf.NameAscii = eng_font
                            tf.NameFarEast = title_cfg["chinese_font"]
                            tf.Size = title_cfg["font_size"]
                            tf.Bold = title_cfg.get("bold", False)

                            pf = title_range.ParagraphFormat
                            pf.Alignment = title_cfg.get("alignment", 1)
                            pf.LineUnitBefore = title_cfg.get("space_before", 0.5)
                            pf.LineUnitAfter = title_cfg.get("space_after", 0.0)
                            pf.CharacterUnitFirstLineIndent = 0
                            pf.FirstLineIndent = 0
                            pf.CharacterUnitLeftIndent = 0
                            pf.LeftIndent = 0
                    except:
                        pass

                    # C. 表格整体格式
                    tbl.PreferredWidthType = 2
                    tbl.PreferredWidth = config.table_width_percent
                    tbl.Rows.Alignment = 1

                    # D. 单元格一维遍历与 JSON 规则下发
                    cells = tbl.Range.Cells
                    for j in range(1, cells.Count + 1):
                        cell = cells.Item(j)
                        clean_text = CELL_FULL_NOISE_PATTERN.sub("", cell.Range.Text)

                        if not clean_text:
                            cell.Shading.BackgroundPatternColor = config.empty_cell_color
                            audit_log.empty_cells.append(f"P{page_num}-T{idx}-C{j}")
                        else:
                            f = cell.Range.Font
                            eng_font = cell_cfg["english_font"]
                            f.Name = eng_font
                            f.NameAscii = eng_font
                            f.NameFarEast = cell_cfg["chinese_font"]
                            f.Size = cell_cfg["font_size"]
                            f.Bold = cell_cfg.get("bold", False)

                            cell.VerticalAlignment = 1
                            cell.Range.ParagraphFormat.Alignment = cell_cfg.get("alignment", 1)

                    audit_log.success += 1
                except Exception as e:
                    audit_log.errors += 1
                    audit_log.error_details.append(f"T{idx} 崩溃: {e}")

            doc.Save()
            return True

    except Exception as e:
        raise RuntimeError(f"表格排版引擎崩溃，详情：\n{e!s}")
    finally:
        progress_ui.close()


# ---------------- 4. 最终主控制流 ----------------

if __name__ == "__main__":
    try:
        word_app = win32com.client.GetActiveObject("Word.Application")
    except:
        try:
            word_app = win32com.client.GetActiveObject("KWPS.Application")
        except:
            word_app = None

    if not word_app:
        ModernInfoDialog(
            "运行阻断", "未检测到运行中的 WPS 或 Word 程序。\n\n请先打开需要排版的报告文档！"
        ).show()
    else:
        if word_app.ActiveDocument.Path == "":
            ModernInfoDialog(
                "操作阻断",
                "该文档尚未保存到本地硬盘。\n请先手动保存一次（Ctrl+S）后再执行排版引擎！",
            ).show()
        else:
            # 死锁目标文档
            target_doc = word_app.ActiveDocument
            current_file = target_doc.Name

            if show_ui_and_get_params(current_file) and final_check_summary(current_file):
                print("正在调用外部模块进行静默备份...")
                if backup_current_document(target_doc):
                    try:
                        if process_all_tables(word_app, target_doc):
                            empty_info = "\n".join(audit_log.empty_cells[:15])
                            if len(audit_log.empty_cells) > 15:
                                empty_info += (
                                    f"\n... (余下 {len(audit_log.empty_cells) - 15} 处省略)"
                                )

                            result_msg = (
                                f"✅ 任务完成：{current_file}\n\n"
                                f"成功排版: {audit_log.success} / 共 {audit_log.total} 表\n"
                                f"因页码跳过: {audit_log.skipped} 表\n"
                                f"标红空值: {len(audit_log.empty_cells)} 处\n\n"
                                f"📍 坐标参考（锁定初始位置）：\n{empty_info if audit_log.empty_cells else '无'}"
                            )
                            ModernInfoDialog("执行完毕", result_msg).show()
                    except Exception as e:
                        ModernInfoDialog("运行期异常拦截", str(e)).show()
                else:
                    ModernInfoDialog(
                        "安全熔断",
                        "⚠️ 备份模块(file_utils)返回失败信号！\n\n为防止原文件损坏，排版程序已自动终止。\n请检查当前文档是否已保存，或查看后台报错日志。",
                    ).show()
