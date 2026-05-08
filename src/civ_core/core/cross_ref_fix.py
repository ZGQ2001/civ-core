"""交叉引用修复 —— Core 层。

业务目标：
  扫描当前 Word 文档的所有域（Fields），对类型为 REF (wdFieldRef = 3) 且
  代码里没有 `\\* MERGEFORMAT` 开关的，追加该开关，避免后续编辑时引用文字
  丢失原有字号 / 字体。

三层职责（本模块只占两层）：
  • fix_cross_references(...)  —— 纯算法，接 Word.Document COM 对象，返回 dataclass
  • run_cross_ref_fix(...)     —— 编排层：WordApp + 可选备份 + 调用算法
  • UI 提示 / 确认弹窗          —— 不在本模块（UI 层调 run_*）

工程规范落地：
  ✓ 全开类型注解
  ✓ 参数走 frozen dataclass，禁止裸 dict
  ✓ 资源用 with（WordApp 是 context manager）
  ✓ 异常带上下文，禁止 except: pass
  ✓ 关键节点 logging
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from civ_core.io.word_app import WordApp
from civ_core.models.schema import (
    AppException,
    BackupResult,
    CrossRefFixStats,
    ProgressCallback,
    ProgressUpdate,
)
from civ_core.utils.file_utils import backup_current_document
from civ_core.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 参数契约（per-tool dataclass，与 fix 函数同模块）
# ──────────────────────────────────────────────────────────────────
WD_FIELD_REF: int = 3  # Word: wdFieldRef
DEFAULT_SWITCH: str = r"\* MERGEFORMAT"


@dataclass(slots=True, frozen=True)
class CrossRefFixParams:
    """fix_cross_references / run_cross_ref_fix 的参数契约。

    • dry_run: True 表示只统计、不写回 —— 给「预览有多少要改」用
    • target_field_type: 默认只处理 REF (3)；高级用户可改成其他 wdField* 常量
    • switch: 待追加的开关字符串。默认 r"\\* MERGEFORMAT"
    """

    dry_run: bool = False
    target_field_type: int = WD_FIELD_REF
    switch: str = DEFAULT_SWITCH


# ──────────────────────────────────────────────────────────────────
# 1. 纯算法：传入活动文档对象，返回统计 dataclass
# ──────────────────────────────────────────────────────────────────
def fix_cross_references(
    target_doc: Any,
    params: CrossRefFixParams = CrossRefFixParams(),
    progress: ProgressCallback | None = None,
) -> CrossRefFixStats:
    """遍历文档 Fields，给缺 switch 的 REF 域追加 switch。

    target_doc: win32com 的 Word.Document COM 对象。
    progress:   可选回调；UI 层接住后能在主窗口展示进度环。

    无 UI、无弹窗、无 print。
    """
    try:
        fields = target_doc.Fields
        total = int(fields.Count)
    except Exception as e:
        raise AppException(
            f"读取文档 Fields 集合失败: {e}",
            hint="请确认文档处于编辑状态、未被锁定。",
        ) from e

    log.info("开始扫描交叉引用：共 %d 个域，dry_run=%s", total, params.dry_run)

    stats = CrossRefFixStats(refs_processed=0, refs_updated=0)
    needle = params.switch.upper()

    # COM Fields 集合是 1-indexed
    for i in range(1, total + 1):
        if progress is not None:
            progress(ProgressUpdate(current=i, total=total, message=f"扫描域 {i}/{total}"))

        try:
            f = fields.Item(i)
            if int(f.Type) != params.target_field_type:
                continue

            # 先把 Code.Text 读出来 —— 如果这一步抛异常，本 field 不算「已处理」
            code_text = str(f.Code.Text or "")
            stats.refs_processed += 1

            if needle in code_text.upper():
                continue  # 已经有开关，不动

            if not params.dry_run:
                f.Code.Text = code_text + " " + params.switch
            stats.refs_updated += 1

        except Exception as e:
            # 单个 field 失败不熔断 —— 记日志、继续
            log.warning("处理第 %d 个域失败 (跳过): %s", i, e)
            continue

    log.info(
        "交叉引用扫描完成：REF 域 %d 个，%s %d 个",
        stats.refs_processed,
        "需更新" if params.dry_run else "已追加开关",
        stats.refs_updated,
    )
    return stats


# ──────────────────────────────────────────────────────────────────
# 2. 编排：附着 Word + 可选备份 + 调用算法
# ──────────────────────────────────────────────────────────────────
def run_cross_ref_fix(
    *,
    backup_first: bool = True,
    params: CrossRefFixParams | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[CrossRefFixStats, BackupResult | None]:
    """编排函数：attach Word/WPS → 可选备份 → 跑核心算法 → 返回 (stats, backup)。

    UI worker thread 直接调它；任何业务异常都会以 AppException 子类抛出，
    UI 层 try/except 后用 InfoBar 友好提示用户。
    """
    params = params or CrossRefFixParams()

    with WordApp(require_saved=True, optimize_env=True) as wctx:
        backup: BackupResult | None = None
        if backup_first:
            log.info("执行备份: %s", wctx.doc_name)
            backup = backup_current_document(wctx.active_doc)
            if not backup.success:
                raise AppException(
                    f"备份失败 — 已中止本次修复: {backup.reason}",
                    hint="请确保文档已存盘到本地硬盘，并有写权限。",
                )

        stats = fix_cross_references(wctx.active_doc, params=params, progress=progress)

    return stats, backup
