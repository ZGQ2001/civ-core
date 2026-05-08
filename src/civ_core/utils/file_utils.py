"""通用文档/表格备份工具（无 UI 依赖）。

工程规范落地：
  ✓ tz-aware 时间（datetime + ZoneInfo('Asia/Shanghai')）
  ✓ logger（不再 print）
  ✓ 返回 BackupResult dataclass（不再返回裸 bool）
  ✓ 异常带上下文（不再 except: pass 吞）
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from civ_core.models.schema import BackupResult
from civ_core.utils.logger import get_logger

_TZ = ZoneInfo("Asia/Shanghai")
log = get_logger(__name__)


def backup_current_document(target_obj: Any) -> BackupResult:
    """对 Word.Document / Excel.Workbook COM 对象做时间戳备份。

    备份文件命名规则::
        <原名>_backup_YYYYMMDD_HHMM.<ext>

    返回 BackupResult；调用方根据 .success 决定后续是否继续业务。
    """
    now = datetime.now(tz=_TZ)
    timestamp = now.strftime("%Y%m%d_%H%M")

    # ── ① 取源文件元信息 ──
    try:
        doc_path = str(target_obj.Path or "")
        doc_fullname = str(target_obj.FullName or "")
        doc_name = str(target_obj.Name or "")
    except AttributeError as e:
        msg = f"COM 对象缺少必要属性 (Path/FullName/Name): {e}"
        log.error(msg)
        return BackupResult(success=False, reason=msg, created_at=now)

    if not doc_path or doc_fullname == doc_name:
        msg = "源文件尚未保存到本地磁盘 — 无 Path 信息可推导备份位置"
        log.warning("%s (Name=%s)", msg, doc_name)
        return BackupResult(success=False, source_name=doc_name, reason=msg, created_at=now)

    # ── ② 先把源文件本身存一次（避免备份的是脏拷贝）──
    try:
        target_obj.Save()
    except Exception as e:
        log.exception("源文档 Save() 失败：%s", doc_name)
        return BackupResult(
            success=False,
            source_name=doc_name,
            reason=f"源文档 Save() 失败：{e}",
            created_at=now,
        )

    # ── ③ 推导备份路径 + 鉴别 host (Word/Excel/WPS) ──
    src = Path(doc_fullname)
    backup = src.with_name(f"{src.stem}_backup_{timestamp}{src.suffix}")

    try:
        app_name = str(target_obj.Application.Name or "")
    except Exception as e:
        log.warning("无法读取 target_obj.Application.Name (%s)；按 Word 处理", e)
        app_name = ""

    is_excel_family = any(tag in app_name for tag in ("Excel", "表格", "ET"))

    # ── ④ 执行备份 ──
    try:
        if is_excel_family:
            target_obj.SaveCopyAs(str(backup))
        else:
            app = target_obj.Application
            backup_doc = app.Documents.Add(doc_fullname)
            try:
                backup_doc.SaveAs2(str(backup))
            finally:
                # 0 == wdDoNotSaveChanges
                backup_doc.Close(0)
    except Exception as e:
        log.exception("备份执行失败 (%s → %s)", doc_name, backup.name)
        return BackupResult(
            success=False,
            source_name=doc_name,
            reason=f"备份执行失败：{e}",
            created_at=now,
        )

    log.info("备份完成: %s → %s", doc_name, backup.name)
    return BackupResult(
        success=True,
        backup_path=backup,
        source_name=doc_name,
        created_at=now,
    )


def now_tz() -> datetime:
    """全局统一的「当前时间」入口；任何业务代码要 datetime 都走这里。"""
    return datetime.now(tz=_TZ)
