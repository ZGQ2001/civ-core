"""Word COM 自动化的辅助工具。

与 word_helpers.py 区分：本文件依赖运行中的 Word/WPS 应用对象（COM）；
word_helpers.py 只用 python-docx 离线读写文档。
"""

from contextlib import contextmanager


@contextmanager
def word_optimized_environment(app):
    """挂起 Word/WPS 的耗时选项与弹窗，加速批量改写；退出时安全恢复。

    每个状态独立 try/except —— 防止某个不兼容属性恢复失败连累 ScreenUpdating 没法亮屏。
    """
    states = {}

    try:
        try:
            states["ScreenUpdating"] = app.ScreenUpdating
            app.ScreenUpdating = False
        except Exception:
            pass

        try:
            states["DisplayAlerts"] = app.DisplayAlerts
            app.DisplayAlerts = 0  # wdAlertsNone
        except Exception:
            pass

        try:
            states["Pagination"] = app.Options.Pagination
            app.Options.Pagination = False
        except Exception:
            pass

        try:
            states["CheckSpelling"] = app.Options.CheckSpellingAsYouType
            app.Options.CheckSpellingAsYouType = False
        except Exception:
            pass

        try:
            states["CheckGrammar"] = app.Options.CheckGrammarAsYouType
            app.Options.CheckGrammarAsYouType = False
        except Exception:
            pass

        yield

    finally:
        try:
            if "CheckGrammar" in states:
                app.Options.CheckGrammarAsYouType = states["CheckGrammar"]
        except Exception:
            pass

        try:
            if "CheckSpelling" in states:
                app.Options.CheckSpellingAsYouType = states["CheckSpelling"]
        except Exception:
            pass

        try:
            if "Pagination" in states:
                app.Options.Pagination = states["Pagination"]
        except Exception:
            pass

        try:
            if "DisplayAlerts" in states:
                app.DisplayAlerts = states["DisplayAlerts"]
        except Exception:
            pass

        # 屏幕亮屏必须独立保证执行
        try:
            app.ScreenUpdating = True
        except Exception:
            pass
