"""Word / WPS COM 应用的生命周期管理 —— Stage 2 所有 Word 工具的统一入口。

设计目的：
  把「附着到运行中的 Word/WPS、检查 ActiveDocument 是否已保存、进入优化环境、
   退出时恢复屏幕」这套样板代码，从每个工具脚本里抽出来，变成一个 with 块。

用法::

    from civ_core.io.word_app import WordApp

    with WordApp(require_saved=True) as wctx:
        # wctx 是 WordContext dataclass
        # wctx.app, wctx.active_doc, wctx.host_kind, wctx.doc_path 都可用
        # 里面已自动开启 word_optimized_environment
        do_format(wctx.active_doc)

工程规范落地：
  ✓ 资源用 with 管理（COM dispatch + 优化环境双保险）
  ✓ 业务异常 (WordNotRunningError / DocumentNotSavedError)，UI 可 InfoBar 友好提示
  ✓ logger 记录关键节点（attach 成功/失败、host 类型识别）
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from civ_core.models.schema import (
    DocumentNotSavedError,
    WordContext,
    WordNotRunningError,
)
from civ_core.utils.logger import get_logger
from civ_core.utils.word_com import word_optimized_environment

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# 1. host 探测：依次尝试 Word.Application → KWPS.Application
# ──────────────────────────────────────────────────────────────────
_HOST_CANDIDATES = [
    ("Word.Application", "Word"),
    ("KWPS.Application", "WPS"),  # WPS 兼容模式
    ("Wps.Application", "WPS"),  # WPS 经典模式
]


def _attach_running_app() -> tuple[object, str]:
    """逐个尝试 GetActiveObject，返回 (app_dispatch, host_kind)。

    任意一种都附着成功就返回；全失败抛 WordNotRunningError。
    """
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as e:
        raise WordNotRunningError(
            f"无法 import win32com (pywin32 未安装?): {e}",
            hint="请运行：pip install pywin32",
        ) from e

    last_error: Exception | None = None
    for prog_id, kind in _HOST_CANDIDATES:
        try:
            app = win32com.client.GetActiveObject(prog_id)
            log.info("已附着到 %s (ProgID=%s)", kind, prog_id)
            return app, kind
        except Exception as e:
            log.debug("GetActiveObject(%s) 失败: %s", prog_id, e)
            last_error = e

    raise WordNotRunningError(f"未检测到运行中的 Word/WPS 进程（最后一次尝试失败：{last_error}）")


# ──────────────────────────────────────────────────────────────────
# 2. WordApp 主类
# ──────────────────────────────────────────────────────────────────
class WordApp:
    """Word/WPS COM 应用的生命周期上下文管理器。

    参数::

        require_saved      ActiveDocument 必须已保存到本地（默认 True）。
                          False 时允许新建未存盘的文档（少见）。

        optimize_env       进入时自动开 word_optimized_environment（默认 True）。

    退出时自动：
      • 恢复优化前的 ScreenUpdating / DisplayAlerts 等状态
      • 不会关闭 app / document（用户可能还要继续编辑）
    """

    def __init__(self, *, require_saved: bool = True, optimize_env: bool = True):
        self._require_saved = require_saved
        self._optimize_env = optimize_env
        self._stack = ExitStack()
        self._ctx: WordContext | None = None

    def __enter__(self) -> WordContext:
        app, host_kind = _attach_running_app()

        try:
            active_doc = app.ActiveDocument
        except Exception as e:
            raise WordNotRunningError(
                f"{host_kind} 已运行但没有打开任何文档: {e}",
                hint="请在 Word/WPS 中打开目标文档，然后再次运行该工具。",
            ) from e

        try:
            doc_path_str = str(active_doc.Path or "")
            doc_name = str(active_doc.Name or "")
            doc_full = str(active_doc.FullName or "")
        except Exception as e:
            raise WordNotRunningError(
                f"无法读取 ActiveDocument 元信息: {e}",
            ) from e

        if self._require_saved and (not doc_path_str or doc_full == doc_name):
            raise DocumentNotSavedError(
                f"文档 [{doc_name}] 尚未保存到本地磁盘",
            )

        if self._optimize_env:
            self._stack.enter_context(word_optimized_environment(app))

        self._ctx = WordContext(
            app=app,
            active_doc=active_doc,
            host_kind=host_kind,
            doc_path=Path(doc_full) if doc_full else Path(doc_name),
            doc_name=doc_name,
        )
        log.info("WordApp 上下文就绪: host=%s, doc=%s", host_kind, doc_name)
        return self._ctx

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self._stack.close()
        finally:
            if exc_type is not None:
                log.error("WordApp 退出时业务异常 (%s): %s", exc_type.__name__, exc_val)
            else:
                log.debug("WordApp 上下文正常退出")
