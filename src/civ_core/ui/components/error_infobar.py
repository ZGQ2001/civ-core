"""三段式错误/警告 InfoBar 弹窗（定位 → 原因 → 建议）。

为什么独立成模块：
  • 多个 view 都会用到（plot_curves_view / 后续工具页），抽出来避免重复
  • 三段式文案模板集中维护，以后想改一处搞定
  • 禁止把 traceback 弹给用户 —— 详细堆栈走 logger 写到 logs/app.log；
    InfoBar 上只展示"操作员能动手处理的信息"

三档分级：
  show_error_infobar     红色 · duration=-1（错误必须手动关，避免错过）
  show_warning_infobar   黄色 · 默认 5 秒（校验警告 / 部分失败）
  show_success_infobar   绿色 · 默认 3 秒 · 右上角不打扰

"定位"由异常类型映射出"用户视角的操作名"（如 FileBusyError → "文件被占用"），
调用方还能给一个 where 前缀（如"生成绘图"）让上下文更具体。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

# 异常类型 → 用户视角标题。
# 用类名字符串而不是 isinstance：解耦 ── 后续新工具的异常类型可以直接补条目，
# 不必反向 import 它们。命中失败时退回到 default。
_TITLE_BY_TYPE: dict[str, str] = {
    "ExcelReadError": "Excel 读取失败",
    "FileBusyError": "文件被占用",
    "FileWriteError": "文件写入失败",
    "PlotCurvesError": "绘图任务失败",
    "ConfigError": "配置错误",
}


def _exc_title(exc: BaseException, default: str = "操作失败") -> str:
    return _TITLE_BY_TYPE.get(type(exc).__name__, default)


def _format_content(reason: str, hint: str = "") -> str:
    """组装两段（有 hint）或一段（没有）的 InfoBar.content 文本。

    格式：
      原因：<message>

      建议：<hint>
    """
    parts: list[str] = [f"原因：{reason}"]
    if hint:
        parts.append(f"建议：{hint}")
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────
# 三档对外 API
# ──────────────────────────────────────────────────────────────────
def show_error_infobar(
    parent: QWidget,
    exc: BaseException,
    *,
    where: str = "",
) -> None:
    """红色 InfoBar：操作彻底失败。

    parent  InfoBar 宿主（通常是当前 view 或 MainWindow）
    exc     异常实例（带 hint 字段者优先使用 hint 作为"建议"）
    where   可选前缀，给标题加上"哪一步"上下文，如"生成绘图：文件被占用"
    """
    title = _exc_title(exc)
    if where:
        title = f"{where}：{title}"

    hint = getattr(exc, "hint", "") or ""
    content = _format_content(str(exc), hint)

    InfoBar.error(
        title=title,
        content=content,
        # Vertical 让长 content（含换行）正常竖排展开；Horizontal 会被压成一行
        orient=Qt.Orientation.Vertical,
        isClosable=True,
        duration=-1,  # 错误强制手动关 —— 不能让用户没注意到就消失
        position=InfoBarPosition.TOP,
        parent=parent,
    )


def show_warning_infobar(
    parent: QWidget,
    title: str,
    reason: str,
    hint: str = "",
    *,
    duration: int = 5000,
) -> None:
    """黄色 InfoBar：校验警告 / 部分失败。

    与 show_error_infobar 的区别：警告不带异常对象（用户没操作错，只是"还差点"），
    所以参数是裸字符串。duration 默认 5 秒自动消失。
    """
    InfoBar.warning(
        title=title,
        content=_format_content(reason, hint),
        orient=Qt.Orientation.Vertical,
        isClosable=True,
        duration=duration,
        position=InfoBarPosition.TOP,
        parent=parent,
    )


def show_success_infobar(
    parent: QWidget,
    title: str,
    content: str,
    *,
    duration: int = 3000,
) -> None:
    """绿色 InfoBar：成功反馈。右上角短暂浮现，不打扰用户后续操作。"""
    InfoBar.success(
        title=title,
        content=content,
        orient=Qt.Orientation.Horizontal,  # 成功消息一般短，横排即可
        isClosable=True,
        duration=duration,
        position=InfoBarPosition.TOP_RIGHT,
        parent=parent,
    )
