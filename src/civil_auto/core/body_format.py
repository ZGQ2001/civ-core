"""
===============================================================================
脚本名称：报告正文排版引擎 (body_format.py)
作者：ZGQ
功能概述：
    基于外部 JSON 配置和正则表达式，对 Word 文档的非结构化正文进行特征识别与精准排版。
    V2.2 现代UI修复版：加回防呆确认机制，增强底层异常拦截，防止静默崩溃。
===============================================================================
"""

# ---------------- 基础标准库 ----------------
import json
import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import win32com.client
from common.file_utils import backup_current_document
from common.patterns import (
    APPRAISAL_CONCLUSION_HEADER_PATTERN,
    APPRAISAL_CONCLUSION_L2_PATTERN,
    BASIS_TITLE_PATTERN,
    BLANK_HINT_PATTERN,
    BULLET_LIST_ITEM_PATTERN,
    FIG_OR_TBL_CAPTION_PATTERN,
    HEADING_L1_PATTERN,
    HEADING_L2_PATTERN,
    HEADING_L3_PATTERN,
    NO_INDENT_START_PATTERN,
    NOTE_LABEL_PATTERN,
    NUMBERED_LIST_ITEM_PATTERN,
    SUGGESTION_TITLE_PATTERN,
    clean_word_text,
)
from common.word_com import word_optimized_environment
from ui_components import (
    ModernConfirmDialog,
    ModernInfoDialog,
    ModernParamDialog,
    ModernProgressConsole,
)

# ==================== 板块 1：配置与规则大脑 ====================


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


class ParagraphClassifier:
    def __init__(self):
        self.re_fig_tbl = FIG_OR_TBL_CAPTION_PATTERN
        self.re_note = NOTE_LABEL_PATTERN
        self.re_list_item = NUMBERED_LIST_ITEM_PATTERN
        self.re_blank = BLANK_HINT_PATTERN
        self.re_no_indent = NO_INDENT_START_PATTERN
        self.re_h1 = HEADING_L1_PATTERN
        self.re_h2 = HEADING_L2_PATTERN
        self.re_h3 = HEADING_L3_PATTERN
        self.re_appr_c_h1 = APPRAISAL_CONCLUSION_HEADER_PATTERN
        self.re_appr_c_h2 = APPRAISAL_CONCLUSION_L2_PATTERN
        self.re_basis_title = BASIS_TITLE_PATTERN
        self.re_suggest_title = SUGGESTION_TITLE_PATTERN

    def classify(
        self,
        text,
        list_string="",
        is_in_note_mode=False,
        is_in_basis_mode=False,
        is_in_conclusion_mode=False,
        report_type="检测报告",
    ):
        clean_text = clean_word_text(f"{list_string}{text}")

        if not clean_text:
            return "空行"
        if self.re_blank.search(clean_text):
            return "空白提示"
        if self.re_fig_tbl.match(clean_text):
            return "图表名称"
        # 确保无论“检测报告”还是“鉴定报告”，都能优先拦截注和多行注，切断被误判为标题的可能
        if self.re_note.match(clean_text):
            return "表注说明_起点"
        if is_in_note_mode and self.re_list_item.match(clean_text):
            return "表注说明_延续"

        if report_type == "鉴定报告":
            condensed = clean_text.replace(" ", "").replace("·", "").replace("\u3000", "")
            if condensed == "检测结论与建议" or self.re_suggest_title.match(condensed):
                return "结论一级标题"
            if is_in_conclusion_mode and self.re_appr_c_h2.match(clean_text):
                return "结论二级标题"
            if self.re_h3.match(clean_text):
                return "三级标题"
            if self.re_h2.match(clean_text):
                return "二级标题"
            if self.re_h1.match(clean_text):
                return "一级标题"
            if is_in_basis_mode:
                return "无缩进正文"
            if self.re_no_indent.match(clean_text):
                return "无缩进正文"
            return "标准正文"
        else:
            if self.re_h3.match(clean_text):
                return "三级标题"
            if self.re_h2.match(clean_text):
                return "二级标题"
            if self.re_h1.match(clean_text):
                return "一级标题"
            if is_in_basis_mode:
                return "无缩进正文"
            if self.re_no_indent.match(clean_text):
                return "无缩进正文"
            return "标准正文"


# ==================== 板块 2：交互与参数获取 (UI) ====================


def get_user_params(file_name):
    return ModernParamDialog("正文排版参数设置", file_name, show_width=False).show()


def final_check_summary(file_name, params):
    """【恢复】参数设置后的防呆确认弹窗"""
    summary = (
        f"报告类型: {params['report_type']}\n"
        f"跳过页码: {params['skip_pages'] if params['skip_pages'] else '无'}\n\n"
        "字体、字号及间距将自动从 JSON 配置库读取。\n"
        "确认执行后，将调用静默备份并开始全量排版。"
    )
    # 调用 ModernConfirmDialog
    dialog = ModernConfirmDialog("请最终确认排版清单", f"目标文件: {file_name}", summary)
    return dialog.show()


# ==================== 板块 3：格式引擎 ====================


def apply_paragraph_format(para, style_config, para_type):
    try:
        f = para.Range.Font
        eng_font = style_config.get("english_font", "Times New Roman")
        f.Name = eng_font
        f.NameAscii = eng_font
        f.NameFarEast = style_config.get("chinese_font", "宋体")
        f.Size = style_config.get("font_size", 12.0)
        f.Bold = style_config.get("bold", False)

        pf = para.Format
        pf.Alignment = style_config.get("alignment", 3)
        pf.OutlineLevel = style_config.get("outline_level", 10)
        pf.SpaceBefore = style_config.get("space_before", 0) * 12
        pf.SpaceAfter = style_config.get("space_after", 0) * 12

        ls_rule = style_config.get("line_spacing_rule", 5)
        if ls_rule == 1:
            pf.LineSpacingRule = 1
        elif ls_rule == 0:
            pf.LineSpacingRule = 0
        else:
            pf.LineSpacingRule = 5
            pf.LineSpacing = style_config.get("line_spacing", 1.5) * 12
        pf.DisableLineHeightGrid = False

        pf.CharacterUnitRightIndent = style_config.get("right_indent", 0)
        char_first = style_config.get("first_line_indent", 0)
        pf.CharacterUnitFirstLineIndent = char_first
        if char_first == 0:
            pf.FirstLineIndent = 0
        pf.CharacterUnitLeftIndent = 0
        pf.LeftIndent = 0

        if style_config.get("left_indent_pt", 0) != 0:
            pf.LeftIndent = style_config["left_indent_pt"]
        if style_config.get("first_line_indent_pt", 0) != 0:
            pf.FirstLineIndent = style_config["first_line_indent_pt"]

    except Exception:
        pass


def process_document_body(app, doc, params):
    report_type = params["report_type"]
    skip_pages = params["skip_pages"]

    full_config = load_style_config(report_type)
    classifier = ParagraphClassifier()

    paragraphs = doc.Paragraphs
    total_paras = paragraphs.Count

    progress_ui = ModernProgressConsole("正文自动排版程序", total_paras)

    success_count = 0
    skipped_count = 0
    manual_list_skip_count = 0
    note_mode = basis_mode = conclusion_mode = False

    try:
        with word_optimized_environment(app):
            last_ui_update = time.time()

            for i in range(1, total_paras + 1):
                current_time = time.time()
                if current_time - last_ui_update >= 0.05 or i == total_paras:
                    progress_ui.update_progress(i, f"正在排版: {i}/{total_paras} 段")
                    last_ui_update = current_time

                if progress_ui.is_cancelled:
                    print("【中断】用户手动终止了排版过程。")
                    break

                para = paragraphs.Item(i)

                try:
                    max_skip = max(skip_pages) if skip_pages else 0
                    if skip_pages and i <= (max_skip * 40 + 50):
                        page_num = para.Range.Information(3)
                    else:
                        page_num = 999

                    if page_num in skip_pages:
                        skipped_count += 1
                        continue
                except:
                    pass

                if (
                    para.Range.Information(12)
                    or "目录" in para.Style.NameLocal
                    or "TOC" in para.Style.NameLocal
                ):
                    skipped_count += 1
                    continue

                text = para.Range.Text
                list_str = para.Range.ListFormat.ListString
                clean_t = text.strip()

                is_basis_header = classifier.re_basis_title.match(clean_t)
                is_suggest_header = classifier.re_suggest_title.match(clean_t.replace(" ", ""))

                has_image = False
                try:
                    if para.Range.InlineShapes.Count > 0:
                        has_image = True
                except:
                    pass

                if has_image:
                    para_type = "图片"
                else:
                    para_type = classifier.classify(
                        text, list_str, note_mode, basis_mode, conclusion_mode, report_type
                    )

                if para_type == "结论一级标题":
                    conclusion_mode = True
                elif para_type == "一级标题":
                    conclusion_mode = False

                if is_basis_header:
                    basis_mode = True
                elif para_type in [
                    "一级标题",
                    "二级标题",
                    "三级标题",
                    "结论一级标题",
                    "结论二级标题",
                ]:
                    basis_mode = False

                if para_type == "表注说明_起点":
                    note_mode = True
                elif para_type not in ["表注说明_延续", "空行"]:
                    note_mode = False

                if para_type == "标准正文":
                    if NUMBERED_LIST_ITEM_PATTERN.match(text.strip()):
                        manual_list_skip_count += 1
                        try:
                            para.Range.Font.Color = 255
                        except:
                            pass
                        continue

                if para_type == "标准正文" and BULLET_LIST_ITEM_PATTERN.match(text.strip()):
                    para_type = "无缩进正文"

                if para_type in full_config:
                    apply_paragraph_format(para, full_config[para_type], para_type)
                    success_count += 1

    except Exception as e:
        # 【拦截】如果底层崩溃，将异常抛出给外层
        raise RuntimeError(f"排版底层引擎崩溃，详情：\n{e!s}")
    finally:
        # 【拦截】不管成功还是失败，强制销毁进度条，确保后面的弹窗能顺利弹出
        progress_ui.close()

    return success_count, skipped_count, manual_list_skip_count


# ==================== 最终主控流 ====================

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
            "运行阻断", "未检测到运行中的 WPS 或 Word 程序。\n\n请先打开需要排版的报告文档！"
        ).show()
    else:
        if app.ActiveDocument.Path == "":
            ModernInfoDialog(
                "操作阻断",
                "该文档尚未保存到本地硬盘。\n请先手动保存一次（Ctrl+S）后再执行排版引擎！",
            ).show()
        else:
            # 【核心修复 1】：在任何操作前，立刻“死锁”当前活动文档的内存对象
            target_doc = app.ActiveDocument
            current_file = target_doc.Name

            # 呼出参数填写卡片
            run_params = get_user_params(current_file)

            if run_params is None:
                pass  # 用户取消了参数面板
            else:
                if final_check_summary(current_file, run_params):
                    print("正在调用外部模块进行静默备份...")
                    # 即使 backup_current_document 导致 WPS 焦点偏移，target_doc 依然指向原文档
                    if backup_current_document(target_doc):
                        try:
                            # 【核心修复 2】：将锁定的 target_doc 显式传入排版引擎
                            succ_cnt, skip_cnt, manual_cnt = process_document_body(
                                app, target_doc, run_params
                            )

                            msg = (
                                f"✅ 正文排版任务完成！\n\n"
                                f"1. 成功刷入格式：{succ_cnt} 段\n"
                                f"2. 标红待核列表：{manual_cnt} 段\n"
                                f"3. 规则/页码跳过：{skip_cnt} 段\n\n"
                                f"提示：文档中红色段落已自动跳过排版，请人工核对。"
                            )
                            ModernInfoDialog("执行完毕", msg).show()

                        except Exception as e:
                            ModernInfoDialog("运行期异常拦截", str(e)).show()
                    else:
                        ModernInfoDialog(
                            "安全熔断",
                            "⚠️ 备份模块(file_utils)返回失败信号！\n\n为防止原文件损坏，排版程序已自动终止。\n请检查当前文档是否已保存，或查看后台报错日志。",
                        ).show()
