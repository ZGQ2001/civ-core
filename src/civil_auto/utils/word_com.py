"""Word/WPS COM 自动化的辅助工具（无 UI 依赖）。

设计要点：
  • 与 word_helpers.py 区分 —— 本文件依赖运行中的 COM 对象
  • word_optimized_environment 在进入时挂起耗时选项、退出时安全恢复
  • 任何「恢复失败」走 logger.warning 而不是 except: pass —— 这样下次发生时能看到
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from civil_auto.utils.logger import get_logger

log = get_logger(__name__)


def _try_set(label: str, fn: Callable[[], None]) -> None:
    """统一封装「尝试改一项 COM 属性，失败 warn 不抛」的模式。

    比散落 try/except 干净，且任何失败都会进日志，事后可查。
    """
    try:
        fn()
    except Exception as e:
        # COM 不同 host (Word vs WPS vs ET) 兼容差异 — warn 即可
        log.warning("无法设置 COM 属性 [%s]: %s", label, e)


@contextmanager
def word_optimized_environment(app: Any) -> Iterator[None]:
    """挂起 Word/WPS 的耗时选项与弹窗，加速批量改写；退出时安全恢复。

    用法::

        with word_optimized_environment(app):
            # 大量 Find/Replace、表格遍历...

    每个状态独立 try/except —— 防止某个不兼容属性恢复失败连累 ScreenUpdating
    没法亮屏。所有失败都会进日志（debug/warning 两档），不会静默吞。
    """
    states: dict[str, Any] = {}

    # ── 进入：保存当前态、关闭耗时选项 ──
    def _capture(
        label: str, getter: Callable[[], Any], setter: Callable[[Any], None], disabled_value: Any
    ) -> None:
        try:
            states[label] = getter()
        except Exception as e:
            log.debug("读取 [%s] 失败（host 不支持）: %s", label, e)
            return
        _try_set(label, lambda: setter(disabled_value))

    _capture(
        "ScreenUpdating",
        lambda: app.ScreenUpdating,
        lambda v: setattr(app, "ScreenUpdating", v),
        False,
    )
    _capture(
        "DisplayAlerts", lambda: app.DisplayAlerts, lambda v: setattr(app, "DisplayAlerts", v), 0
    )  # wdAlertsNone
    _capture(
        "Pagination",
        lambda: app.Options.Pagination,
        lambda v: setattr(app.Options, "Pagination", v),
        False,
    )
    _capture(
        "CheckSpelling",
        lambda: app.Options.CheckSpellingAsYouType,
        lambda v: setattr(app.Options, "CheckSpellingAsYouType", v),
        False,
    )
    _capture(
        "CheckGrammar",
        lambda: app.Options.CheckGrammarAsYouType,
        lambda v: setattr(app.Options, "CheckGrammarAsYouType", v),
        False,
    )

    log.debug("Word optimized env entered (captured %d states)", len(states))

    try:
        yield
    finally:
        # ── 退出：按反向顺序恢复 ──
        for label, restore in [
            ("CheckGrammar", lambda v: setattr(app.Options, "CheckGrammarAsYouType", v)),
            ("CheckSpelling", lambda v: setattr(app.Options, "CheckSpellingAsYouType", v)),
            ("Pagination", lambda v: setattr(app.Options, "Pagination", v)),
            ("DisplayAlerts", lambda v: setattr(app, "DisplayAlerts", v)),
        ]:
            if label in states:
                _try_set(f"restore.{label}", lambda r=restore, l=label: r(states[l]))

        # 屏幕亮屏必须独立保证执行 —— 任何前面的失败都不能影响这条
        _try_set("restore.ScreenUpdating", lambda: setattr(app, "ScreenUpdating", True))

        log.debug("Word optimized env exited (restored)")
