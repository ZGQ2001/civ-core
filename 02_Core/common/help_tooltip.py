"""[?] 悬停帮助气泡。

用法:
    from common.help_tooltip import attach_help, HelpIcon

    # 方式 A：给任何 widget 挂帮助文本（鼠标悬停时显示气泡）
    attach_help(my_button, "点这里会备份当前文档后自动套用样式。")

    # 方式 B：用现成的 [?] 图标小控件，专门放在表单字段旁边
    HelpIcon(parent, text="这个字段填 Excel 中的列名（带空格也行，工具会容差匹配）").pack(side="left")
"""

import tkinter as tk

import customtkinter as ctk


class _Tooltip:
    """轻量悬浮气泡：鼠标进入 widget 后 400ms 弹出，离开即消失。"""

    DELAY_MS = 400
    OFFSET_X = 18
    OFFSET_Y = 12
    WRAP_LEN = 320

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _evt) -> None:
        self._cancel_pending()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _on_leave(self, _evt) -> None:
        self._cancel_pending()
        self._hide()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + self.OFFSET_X
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + self.OFFSET_Y
        except Exception:
            return

        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tip.attributes("-topmost", True)

        # 适配亮/暗主题，挑个柔和的背景
        appearance = ctk.get_appearance_mode().lower()
        bg = "#2a2a2a" if appearance == "dark" else "#fffce8"
        fg = "#f5f5f5" if appearance == "dark" else "#222222"

        frame = tk.Frame(
            tip,
            background=bg,
            borderwidth=1,
            relief="solid",
            highlightbackground="#666",
            highlightthickness=1,
        )
        frame.pack()
        label = tk.Label(
            frame,
            text=self.text,
            justify="left",
            background=bg,
            foreground=fg,
            font=("微软雅黑", 10),
            padx=10,
            pady=6,
            wraplength=self.WRAP_LEN,
        )
        label.pack()
        self._tip = tip

    def _hide(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def attach_help(widget, text: str) -> _Tooltip:
    """给任何 widget 加悬停帮助。返回 Tooltip 对象（一般用不到）。"""
    return _Tooltip(widget, text)


class HelpIcon(ctk.CTkLabel):
    """[?] 圆形帮助图标。鼠标悬停时显示给定的提示文本。

    样式刻意做小一点，用在表单字段标签的右侧不抢戏。
    """

    def __init__(self, master, text: str, **kwargs):
        kwargs.setdefault("text", " ⓘ ")
        kwargs.setdefault("font", ("微软雅黑", 11, "bold"))
        kwargs.setdefault("text_color", ("gray45", "gray70"))
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("width", 22)
        kwargs.setdefault("cursor", "question_arrow")
        super().__init__(master, **kwargs)
        attach_help(self, text)
