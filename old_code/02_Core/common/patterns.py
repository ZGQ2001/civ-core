"""项目内复用的正则与替换模式。

按用途分组：
    1. 题注 / 编号        —— FIG_PATTERN, FIG_OR_TBL_CAPTION_PATTERN
    2. 标题层级            —— HEADING_L1/L2/L3_PATTERN, APPRAISAL_*, BASIS_TITLE_PATTERN, ...
    3. 列表项              —— NUMBERED_LIST_ITEM_PATTERN, BULLET_LIST_ITEM_PATTERN
    4. 特殊段落            —— NOTE_LABEL_PATTERN, BLANK_HINT_PATTERN, NO_INDENT_START_PATTERN
    5. Word 控制字符清洗   —— WORD_FIELD_CODE_PATTERN, WORD_CONTROL_CHARS_PATTERN, CELL_*
    6. Word Find 通配符    —— WordWildcards（注意：Word COM 的通配符，不是 Python re！）

设计原则：
    - 模块顶层只暴露 re.Pattern 对象；想看正则字符串本身用 .pattern 属性即可。
    - Word 通配符与 Python re 严格区分：前者放在 WordWildcards 类里以纯字符串形式存放。
    - 第二个工具用到同一段模式 = 上提到这里，避免散落复制。
"""

import re

# ============================================================
# 1. 题注 / 编号
# ============================================================
# "图 N / 图N"，捕获组 1 = 数字部分。
# 用途：sort_photos / renumber_photos 在 Word 表格里识别题注编号。
FIG_PATTERN_STR: str = r"图\s*(\d+)"
FIG_PATTERN: re.Pattern = re.compile(FIG_PATTERN_STR)

# 行首 "图/表 N"（含级联编号 1.2.3），捕获组 1=种类("图"/"表")，组 2=完整编号串。
# 用途：body_format 段落分类器识别图表名行。
FIG_OR_TBL_CAPTION_PATTERN: re.Pattern = re.compile(r"^\s*(图|表)\s*(\d+(\.\d+)*)")


# ============================================================
# 2. 标题层级
# ============================================================
# 一级：行首"1 " / "1. " / "一、" / "二." / "三 " 等
HEADING_L1_PATTERN: re.Pattern = re.compile(
    r"^(\d+[\.\s　\t]+|[一二三四五六七八九十]+[、\.\s　\t]+)"
)
# 二级：行首 "1.2" 或 "1．2"
HEADING_L2_PATTERN: re.Pattern = re.compile(r"^\d+[\.．]\d+[\s　\t]*")
# 三级：行首 "1.2.3"
HEADING_L3_PATTERN: re.Pattern = re.compile(r"^\d+[\.．]\d+[\.．]\d+[\s　\t]*")

# 鉴定报告专属："检测结论与建议"（容忍 WPS 把每个字撑开为散字间距，比如 "检 测 结 论 与 建 议"）
APPRAISAL_CONCLUSION_HEADER_PATTERN: re.Pattern = re.compile(
    r"^[检\s·]*测[\s·]*结[\s·]*论[\s·]*与[\s·]*建[\s·]*议$"
)
# 鉴定结论二级标题：行首数字 + 中文标题文字（"1 主要结论"）
APPRAISAL_CONCLUSION_L2_PATTERN: re.Pattern = re.compile(r"^\d+[\.．\s　\t]+[一-龥]+")

# "检测依据" / "鉴定依据" 标题（行首允许有数字编号前缀）
BASIS_TITLE_PATTERN: re.Pattern = re.compile(r"^[\d\.．\s　\t]*(检测|鉴定)依据.*")
# "处理建议" 标题（散字间距版）
SUGGESTION_TITLE_PATTERN: re.Pattern = re.compile(r"^[处\s]*理[\s]*建[\s]*议$")


# ============================================================
# 3. 列表项 / Bullet
# ============================================================
# 数字 / 圈号列表："1." "1、" "1）" "1)" "①…⑩"
NUMBERED_LIST_ITEM_PATTERN: re.Pattern = re.compile(r"^(\d+[.、）\)]|[①②③④⑤⑥⑦⑧⑨⑩])")
# Bullet 列表："• " "- " "* "
BULLET_LIST_ITEM_PATTERN: re.Pattern = re.compile(r"^[\s]*[•\-*]\s+")


# ============================================================
# 4. 特殊段落
# ============================================================
# 表注/说明起点："注：" "说明:" "注 :" 等
NOTE_LABEL_PATTERN: re.Pattern = re.compile(r"^\s*(注|说明)\s*[：:]")

# "(本页)以下空白" 提示行（括号、"本页" 二字均可省）
BLANK_HINT_PATTERN: re.Pattern = re.compile(r".*[（(]?(本页)?以下空白[）)].*")

# 行首是书名号 / 引文 / 半/全角括号 —— 表示"无缩进正文"
NO_INDENT_START_PATTERN: re.Pattern = re.compile(r"^\s*[《\(\[（]")


# ============================================================
# 5. Word 控制字符清洗
# ============================================================
# Word 域代码整段（\x13 起、\x14 终），用 .* 非贪婪
WORD_FIELD_CODE_PATTERN: re.Pattern = re.compile(r"\x13.*?\x14")
# 段落中残留的 Word 控制字符集合：
#   \x13/\x14 域起止、\x15 域结束符、\x07 表格单元格分隔、\x01/\x02 内嵌对象/特殊
WORD_CONTROL_CHARS_PATTERN: re.Pattern = re.compile(r"[\x13\x14\x15\x07\x01\x02]")

# 表格单元格清洗：仅去掉空白 + BEL（\x07）
CELL_BLANK_NOISE_PATTERN: re.Pattern = re.compile(r"[\s\x07]")
# 表格单元格清洗（彻底版）：换行 + 空白 + BEL
CELL_FULL_NOISE_PATTERN: re.Pattern = re.compile(r"[\r\n\x07\s]")


def clean_word_text(text: str) -> str:
    """清洗 Word 段落原始文本：剥离域代码、控制字符，把 \\xa0 转普通空格，并 strip。

    body_format 的段落分类器拿到 paragraph.Range.Text 后必须先过这一步，
    否则 \\x13域\\x14 这种隐藏内容会让正则误判。
    """
    cleaned = WORD_FIELD_CODE_PATTERN.sub("", text)
    cleaned = WORD_CONTROL_CHARS_PATTERN.sub("", cleaned).replace("\xa0", " ").strip()
    return cleaned


# ============================================================
# 6. Word Find 通配符（仅供 Word COM 使用，不是 Python re！）
# ============================================================
class WordWildcards:
    """Word COM 的 Find/Replace 通配符规则集合。

    重要：以下字符串是 Word 通配符语法，不能 re.compile。
    Word 通配符速查：
        @       = 一个或多个前述字符（相当于 re 的 +）
        [!x]    = 除 x 之外的任意字符
        \\1     = 反向引用第 1 个分组（Word 用单反斜杠，不是 Python 的 \\\\1）

    用法（参考 bracket_format.py）：
        for find_pat, replace_pat, use_wildcards in WordWildcards.bracket_normalize_rules():
            fnd.Execute(FindText=find_pat, ReplaceWith=replace_pat,
                        MatchWildcards=use_wildcards, Replace=2, ...)
    """

    # 简单字面量替换（非通配符，wc=False）：括号抹平为全角 + 全角波浪号转半角
    FLAT_REPLACEMENTS: list[tuple[str, str]] = [
        ("(", "（"),
        (")", "）"),
        ("～", "~"),
    ]

    # 技术参数（全角 → 半角）：括号内仅英数 + 常见技术符号
    TECH_PARAM_TO_HALF: list[tuple[str, str]] = [
        (r"（([a-zA-Z0-9 .,/\\_~—–:%°+=±×÷·　-]@)）", r"(\1)"),
    ]

    # 国标/行标代号（半角 → 全角）：以 ≥2 大写字母开头（GB/T、JGJ、DB 等）
    STD_CODE_TO_FULL: list[tuple[str, str]] = [
        (r"\(([A-Z]{2,}[A-Z0-9/ \.:　-]@)\)", r"（\1）"),
    ]

    # 书名号后括号：兜底无前缀的标准/企标（Q/ 开头等）。三种空白前缀分别处理。
    BOOK_TITLE_PAREN_TO_FULL: list[tuple[str, str]] = [
        (r"》\(([!)]@)\)", r"》（\1）"),
        (r"》 \(([!)]@)\)", r"》 （\1）"),
        (r"》　\(([!)]@)\)", r"》　（\1）"),
    ]

    # 中文纯数字层级序号：(1)(2) → （1）（2）
    NUMBER_INDEX_TO_FULL: list[tuple[str, str]] = [
        (r"\(([0-9]@)\)", r"（\1）"),
    ]

    # "第 N" 锚定回半角 —— 抗击 NUMBER_INDEX_TO_FULL 的误伤
    DI_NUMBER_TO_HALF: list[tuple[str, str]] = [
        (r"第（([0-9]@)）", r"第(\1)"),
        (r"第 （([0-9]@)）", r"第 (\1)"),
        (r"第　（([0-9]@)）", r"第　(\1)"),
    ]

    @classmethod
    def bracket_normalize_rules(cls) -> list[tuple[str, str, bool]]:
        """组装"括号半全角纠偏"的完整规则序列（顺序敏感）。

        返回 List[(find_pattern, replace_pattern, use_wildcards)]。
        wc=False 表示按字面量匹配，wc=True 表示启用 Word 通配符。
        """
        result: list[tuple[str, str, bool]] = [(f, r, False) for f, r in cls.FLAT_REPLACEMENTS]
        for group in (
            cls.TECH_PARAM_TO_HALF,
            cls.STD_CODE_TO_FULL,
            cls.BOOK_TITLE_PAREN_TO_FULL,
            cls.NUMBER_INDEX_TO_FULL,
            cls.DI_NUMBER_TO_HALF,
        ):
            result.extend((f, r, True) for f, r in group)
        return result
