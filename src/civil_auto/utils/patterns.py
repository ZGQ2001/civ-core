"""项目内复用的正则与替换模式。

按用途分组：
    1. 题注 / 编号        —— FIG_PATTERN, FIG_OR_TBL_CAPTION_PATTERN
    2. 标题层级            —— HEADING_L1/L2/L3_PATTERN, APPRAISAL_*, BASIS_TITLE_PATTERN, ...
    3. 列表项              —— NUMBERED_LIST_ITEM_PATTERN, BULLET_LIST_ITEM_PATTERN
    4. 特殊段落            —— NOTE_LABEL_PATTERN, BLANK_HINT_PATTERN, NO_INDENT_START_PATTERN
    5. Word 控制字符清洗   —— WORD_FIELD_CODE_PATTERN, WORD_CONTROL_CHARS_PATTERN, CELL_*
    6. Word Find 通配符    —— WordWildcards（注意：Word COM 的通配符，不是 Python re！）
"""

import re

# ============================================================
# 1. 题注 / 编号
# ============================================================
FIG_PATTERN_STR: str = r"图\s*(\d+)"
FIG_PATTERN: re.Pattern = re.compile(FIG_PATTERN_STR)
FIG_OR_TBL_CAPTION_PATTERN: re.Pattern = re.compile(r"^\s*(图|表)\s*(\d+(\.\d+)*)")


# ============================================================
# 2. 标题层级
# ============================================================
HEADING_L1_PATTERN: re.Pattern = re.compile(
    r"^(\d+[\.\s　\t]+|[一二三四五六七八九十]+[、\.\s　\t]+)"
)
HEADING_L2_PATTERN: re.Pattern = re.compile(r"^\d+[\.．]\d+[\s　\t]*")
HEADING_L3_PATTERN: re.Pattern = re.compile(r"^\d+[\.．]\d+[\.．]\d+[\s　\t]*")

APPRAISAL_CONCLUSION_HEADER_PATTERN: re.Pattern = re.compile(
    r"^[检\s·]*测[\s·]*结[\s·]*论[\s·]*与[\s·]*建[\s·]*议$"
)
APPRAISAL_CONCLUSION_L2_PATTERN: re.Pattern = re.compile(r"^\d+[\.．\s　\t]+[一-龥]+")

BASIS_TITLE_PATTERN: re.Pattern = re.compile(r"^[\d\.．\s　\t]*(检测|鉴定)依据.*")
SUGGESTION_TITLE_PATTERN: re.Pattern = re.compile(r"^[处\s]*理[\s]*建[\s]*议$")


# ============================================================
# 3. 列表项 / Bullet
# ============================================================
NUMBERED_LIST_ITEM_PATTERN: re.Pattern = re.compile(r"^(\d+[.、）\)]|[①②③④⑤⑥⑦⑧⑨⑩])")
BULLET_LIST_ITEM_PATTERN: re.Pattern = re.compile(r"^[\s]*[•\-*]\s+")


# ============================================================
# 4. 特殊段落
# ============================================================
NOTE_LABEL_PATTERN: re.Pattern = re.compile(r"^\s*(注|说明)\s*[：:]")
BLANK_HINT_PATTERN: re.Pattern = re.compile(r".*[（(]?(本页)?以下空白[）)].*")
NO_INDENT_START_PATTERN: re.Pattern = re.compile(r"^\s*[《\(\[（]")


# ============================================================
# 5. Word 控制字符清洗
# ============================================================
WORD_FIELD_CODE_PATTERN: re.Pattern = re.compile(r"\x13.*?\x14")
WORD_CONTROL_CHARS_PATTERN: re.Pattern = re.compile(r"[\x13\x14\x15\x07\x01\x02]")
CELL_BLANK_NOISE_PATTERN: re.Pattern = re.compile(r"[\s\x07]")
CELL_FULL_NOISE_PATTERN: re.Pattern = re.compile(r"[\r\n\x07\s]")


def clean_word_text(text: str) -> str:
    """清洗 Word 段落原始文本：剥离域代码、控制字符，把 \\xa0 转普通空格，并 strip。"""
    cleaned = WORD_FIELD_CODE_PATTERN.sub("", text)
    cleaned = WORD_CONTROL_CHARS_PATTERN.sub("", cleaned).replace("\xa0", " ").strip()
    return cleaned


# ============================================================
# 6. Word Find 通配符（仅供 Word COM 使用，不是 Python re！）
# ============================================================
class WordWildcards:
    """Word COM 的 Find/Replace 通配符规则集合。"""

    FLAT_REPLACEMENTS: list[tuple[str, str]] = [
        ("(", "（"),
        (")", "）"),
        ("～", "~"),
    ]

    TECH_PARAM_TO_HALF: list[tuple[str, str]] = [
        (r"（([a-zA-Z0-9 .,/\\_~—–:%°+=±×÷·　-]@)）", r"(\1)"),
    ]

    STD_CODE_TO_FULL: list[tuple[str, str]] = [
        (r"\(([A-Z]{2,}[A-Z0-9/ \.:　-]@)\)", r"（\1）"),
    ]

    BOOK_TITLE_PAREN_TO_FULL: list[tuple[str, str]] = [
        (r"》\(([!)]@)\)", r"》（\1）"),
        (r"》 \(([!)]@)\)", r"》 （\1）"),
        (r"》　\(([!)]@)\)", r"》　（\1）"),
    ]

    NUMBER_INDEX_TO_FULL: list[tuple[str, str]] = [
        (r"\(([0-9]@)\)", r"（\1）"),
    ]

    DI_NUMBER_TO_HALF: list[tuple[str, str]] = [
        (r"第（([0-9]@)）", r"第(\1)"),
        (r"第 （([0-9]@)）", r"第 (\1)"),
        (r"第　（([0-9]@)）", r"第　(\1)"),
    ]

    @classmethod
    def bracket_normalize_rules(cls) -> list[tuple[str, str, bool]]:
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
