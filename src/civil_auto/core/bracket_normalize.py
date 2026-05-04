"""文档全局括号半全角纠偏 —— Core 层。

业务目标：
  按 utils.patterns.WordWildcards.bracket_normalize_rules() 提供的顺序敏感规则
  序列，调 Word.Range.Find.Execute 对全文做批量替换：
    1. 普通括号抹平为全角
    2. 技术参数（纯英数+技术符号）转半角
    3. 国标/书名号/数字序号锁定全角
    4. "第N..." 反向修正回半角

三层职责（本模块只占两层）：
  • normalize_brackets(...)      —— 纯算法：接 Word.Document COM 对象，返回 BracketFixStats
  • run_bracket_normalize(...)   —— 编排：WordApp + 可选备份 + 调算法
  • UI 弹窗 / 成功提示             —— 不在本模块（UI 层调 run_*）

工程规范落地：
  ✓ 全开类型注解
  ✓ 参数 frozen dataclass，规则列表也 dataclass 化（不裸传 tuple）
  ✓ Word.Range 用 Duplicate 隔离避免 caller 污染
  ✓ 单条规则失败不熔断，logger.warning 记下继续
  ✓ 关键节点 logging
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from civil_auto.io.word_app import WordApp
from civil_auto.models.schema import (
    AppException,
    BackupResult,
    BracketFixStats,
    ProgressCallback,
    ProgressUpdate,
)
from civil_auto.utils.file_utils import backup_current_document
from civil_auto.utils.logger import get_logger
from civil_auto.utils.patterns import WordWildcards

log = get_logger(__name__)


# Word COM constants
WD_REPLACE_NONE: int = 0
WD_REPLACE_ALL: int = 2
WD_FIND_CONTINUE: int = 1
WD_FIND_STOP: int = 0


# ──────────────────────────────────────────────────────────────────
# 1. 规则契约（dataclass，禁止 caller 传裸 tuple）
# ──────────────────────────────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class BracketRule:
    """单条 Word Find/Replace 规则。"""

    find_pattern: str
    replace_pattern: str
    use_wildcards: bool

    @classmethod
    def from_tuple(cls, t: tuple[str, str, bool]) -> BracketRule:
        return cls(find_pattern=t[0], replace_pattern=t[1], use_wildcards=t[2])


def default_rules() -> list[BracketRule]:
    """从 utils.patterns 提取默认规则集，转 dataclass。"""
    return [BracketRule.from_tuple(t) for t in WordWildcards.bracket_normalize_rules()]


# ──────────────────────────────────────────────────────────────────
# 2. 工具函数参数契约
# ──────────────────────────────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class BracketNormalizeParams:
    """normalize_brackets / run_bracket_normalize 的参数契约。

    • dry_run: True 表示只统计、不写回（自动开启 count_replacements）
    • count_replacements: 精确统计每条规则的命中数；开启会让运行时间约翻倍
                          （需要先以 wdReplaceNone 扫一遍计数再 wdReplaceAll）
    • rules: None 表示用默认规则集；测试 / 高级用户可传自定义列表
    """

    dry_run: bool = False
    count_replacements: bool = False
    rules: tuple[BracketRule, ...] | None = None  # tuple 才能 frozen


# ──────────────────────────────────────────────────────────────────
# 3. 内部工具：精确计数 + 单规则执行
# ──────────────────────────────────────────────────────────────────
def _count_matches(target_doc: Any, rule: BracketRule) -> int:
    """用 wdReplaceNone 扫描计数。不修改文档。

    用 .Duplicate 隔离 search range，避免污染 caller 的 Selection / Content 焦点。
    """
    try:
        search = target_doc.Content.Duplicate
    except Exception as e:
        log.warning("获取 Content.Duplicate 失败 (无法计数): %s", e)
        return 0

    count = 0
    fnd = search.Find
    fnd.ClearFormatting()
    fnd.Replacement.ClearFormatting()

    # 防御：极端情况死循环兜底
    safety_limit = 100_000
    while count < safety_limit:
        try:
            found = bool(
                fnd.Execute(
                    FindText=rule.find_pattern,
                    MatchCase=False,
                    MatchWholeWord=False,
                    MatchWildcards=rule.use_wildcards,
                    MatchSoundsLike=False,
                    MatchAllWordForms=False,
                    Forward=True,
                    Wrap=WD_FIND_STOP,  # 不要循环回开头，否则永远 True
                    Format=False,
                    Replace=WD_REPLACE_NONE,
                )
            )
        except Exception as e:
            log.warning("计数 Execute 失败 (规则=%s): %s", rule.find_pattern, e)
            break

        if not found:
            break
        count += 1
        # 推进 search range 到当前匹配之后
        try:
            if search.End >= target_doc.Content.End:
                break
            search.Start = search.End
            search.End = target_doc.Content.End
        except Exception as e:
            log.warning("推进 search range 失败: %s", e)
            break
    else:
        log.warning("规则 [%s] 计数命中安全上限 %d，可能模式异常", rule.find_pattern, safety_limit)

    return count


def _apply_rule_replace_all(target_doc: Any, rule: BracketRule) -> None:
    """用 wdReplaceAll 对全文执行一次替换。"""
    rng = target_doc.Content
    fnd = rng.Find
    fnd.ClearFormatting()
    fnd.Replacement.ClearFormatting()

    fnd.Execute(
        FindText=rule.find_pattern,
        MatchCase=False,
        MatchWholeWord=False,
        MatchWildcards=rule.use_wildcards,
        MatchSoundsLike=False,
        MatchAllWordForms=False,
        Forward=True,
        Wrap=WD_FIND_CONTINUE,
        Format=False,
        ReplaceWith=rule.replace_pattern,
        Replace=WD_REPLACE_ALL,
    )


# ──────────────────────────────────────────────────────────────────
# 4. 纯算法
# ──────────────────────────────────────────────────────────────────
def normalize_brackets(
    target_doc: Any,
    params: BracketNormalizeParams = BracketNormalizeParams(),
    progress: ProgressCallback | None = None,
) -> BracketFixStats:
    """对全文按规则序列执行括号纠偏，返回统计 dataclass。

    无 UI、无弹窗、无 print；进度通过 ProgressCallback 回调。
    """
    rules: list[BracketRule] = list(params.rules) if params.rules else default_rules()
    total = len(rules)
    log.info(
        "开始括号纠偏：%d 条规则, dry_run=%s, count=%s",
        total,
        params.dry_run,
        params.count_replacements,
    )

    stats = BracketFixStats(rules_applied=0, total_replacements=0)
    must_count = params.dry_run or params.count_replacements

    for i, rule in enumerate(rules, start=1):
        if progress is not None:
            progress(
                ProgressUpdate(
                    current=i,
                    total=total,
                    message=f"应用括号规则 {i}/{total}",
                )
            )

        try:
            n_hits = 0
            if must_count:
                n_hits = _count_matches(target_doc, rule)

            if not params.dry_run:
                _apply_rule_replace_all(target_doc, rule)

            stats.rules_applied += 1
            stats.total_replacements += n_hits

            if must_count:
                log.debug("规则 %d/%d 命中 %d 次: %s", i, total, n_hits, rule.find_pattern)

        except Exception as e:
            # 单条规则失败不熔断
            log.warning("规则 %d/%d 执行失败 (跳过): %s | rule=%s", i, total, e, rule.find_pattern)
            continue

    log.info(
        "括号纠偏完成：%d/%d 条规则成功，total_replacements=%s",
        stats.rules_applied,
        total,
        stats.total_replacements if must_count else "(未启用计数)",
    )
    return stats


# ──────────────────────────────────────────────────────────────────
# 5. 编排：WordApp + 可选备份 + 调算法
# ──────────────────────────────────────────────────────────────────
def run_bracket_normalize(
    *,
    backup_first: bool = True,
    params: BracketNormalizeParams | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[BracketFixStats, BackupResult | None]:
    """编排函数：attach Word/WPS → 可选备份 → 跑核心算法 → 返回 (stats, backup)。

    业务异常以 AppException 子类抛出，UI 用 InfoBar 友好提示。
    """
    params = params or BracketNormalizeParams()

    with WordApp(require_saved=True, optimize_env=True) as wctx:
        backup: BackupResult | None = None
        if backup_first:
            log.info("执行备份: %s", wctx.doc_name)
            backup = backup_current_document(wctx.active_doc)
            if not backup.success:
                raise AppException(
                    f"备份失败 — 已中止本次纠偏: {backup.reason}",
                    hint="请确保文档已存盘到本地硬盘，并有写权限。",
                )

        stats = normalize_brackets(wctx.active_doc, params=params, progress=progress)

    return stats, backup
