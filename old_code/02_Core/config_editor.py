"""
报告样式配置可视化编辑器 (config_editor.py)

可视化编辑 04_Config/report_style_config.json，避免手改 JSON 出错。
左侧选"报告类型 + 段落类型"，右侧表单编辑该段落的字体/字号/缩进/行距等。

业务逻辑（load/save_config）纯参数，可被其他工具 import 复用；UI 在 _main 内。
"""

import json
import os
import sys
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from tkinter import messagebox

import customtkinter as ctk
from common.io_helpers import enable_line_buffered_stdout

# ==========================================
# 模块 0：常量与字段定义
# ==========================================
DEFAULT_CONFIG_PATH = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "04_Config", "report_style_config.json")
)

# 对齐方式枚举：值 → 显示文本
ALIGNMENT_OPTIONS: dict[int, str] = {
    0: "0 - 左对齐",
    1: "1 - 居中",
    2: "2 - 右对齐",
    3: "3 - 两端对齐",
}
LINE_SPACING_RULE_OPTIONS: dict[int, str] = {
    0: "0 - 单倍行距",
    1: "1 - 1.5 倍行距",
    5: "5 - 多倍行距(读 line_spacing)",
}
OUTLINE_LEVEL_OPTIONS: dict[int, str] = {
    i: f"{i} - {'大纲' if i <= 9 else '正文'}" for i in range(1, 11)
}

COMMON_CHINESE_FONTS = ["宋体", "仿宋", "黑体", "微软雅黑", "楷体", "等线"]
COMMON_ENGLISH_FONTS = ["Times New Roman", "Arial", "Calibri", "Consolas"]

# 字段渲染说明：(字段名, 显示标签, 控件类型, 选项)
# 控件类型: text / float / int / bool / enum_int / combo_text
FIELD_SCHEMA = [
    ("chinese_font", "中文字体", "combo_text", COMMON_CHINESE_FONTS),
    ("english_font", "英文字体", "combo_text", COMMON_ENGLISH_FONTS),
    ("font_size", "字号 (磅)", "float", None),
    ("bold", "加粗", "bool", None),
    ("alignment", "对齐方式", "enum_int", ALIGNMENT_OPTIONS),
    ("outline_level", "大纲级别", "enum_int", OUTLINE_LEVEL_OPTIONS),
    ("space_before", "段前间距 (倍)", "float", None),
    ("space_after", "段后间距 (倍)", "float", None),
    ("line_spacing_rule", "行距规则", "enum_int", LINE_SPACING_RULE_OPTIONS),
    ("line_spacing", "行距值 (规则=5时)", "float", None),
    ("first_line_indent", "首行缩进 (字符)", "float", None),
    ("right_indent", "右缩进 (字符)", "float", None),
    ("left_indent_pt", "左缩进绝对值 (磅)", "float", None),
    ("first_line_indent_pt", "首行缩进绝对值 (磅)", "float", None),
]


# ==========================================
# 模块 1：核心业务（纯参数）
# ==========================================
def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """读取样式配置 JSON。失败抛 FileNotFoundError / JSONDecodeError。"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"未找到配置文件: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """写回样式配置 JSON（保持 utf-8 + 2 空格缩进 + 中文不转义）。"""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def get_report_types(config: dict[str, Any]) -> list:
    """从顶层 JSON 抽出报告类型列表，过滤以 _ 开头的注释字段。"""
    return [k for k in config.keys() if not k.startswith("_")]


def get_paragraph_types(config: dict[str, Any], report_type: str) -> list:
    """从某报告类型下抽出段落类型列表，过滤以 _ 开头的注释字段。"""
    if report_type not in config:
        return []
    return [k for k in config[report_type].keys() if not k.startswith("_")]


# ==========================================
# 模块 2：UI 流程
# ==========================================
class ConfigEditorPanel(ctk.CTkFrame):
    """样式配置可视化编辑器 —— CTkFrame，可被嵌入任意父容器。

    主控制台 dashboard 把它 .pack() 进右侧内容区即可，无需 subprocess。
    ConfigEditorApp 则把它包在独立的 CTk 窗口里，命令行直接跑时用。
    """

    def __init__(self, master, config_path: str = DEFAULT_CONFIG_PATH, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self.config_path = config_path
        self.config: dict[str, Any] = {}
        self.dirty: bool = False
        self.field_widgets: dict[str, tuple[str, Any]] = {}

        try:
            self.config = load_config(self.config_path)
        except Exception as e:
            messagebox.showerror("加载失败", f"读取配置文件出错:\n{e}")
            ctk.CTkLabel(
                self, text=f"⚠ 配置文件加载失败:\n{e}", font=("微软雅黑", 12), text_color="#aa3333"
            ).pack(pady=20)
            return

        self._build_layout()
        self._refresh_paragraph_list()

    # ------------ 布局构建 ------------
    def _build_layout(self) -> None:
        # 顶部：当前文件 + 保存按钮
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(
            header,
            text=f"配置文件：{self.config_path}",
            font=("微软雅黑", 11),
            text_color="gray50",
        ).pack(side="left")

        self.btn_save = ctk.CTkButton(
            header,
            text="💾 保存",
            width=100,
            height=32,
            font=("微软雅黑", 12, "bold"),
            command=self._save,
        )
        self.btn_save.pack(side="right", padx=4)

        ctk.CTkButton(
            header,
            text="🔄 重新加载",
            width=100,
            height=32,
            fg_color="gray40",
            font=("微软雅黑", 12),
            command=self._reload,
        ).pack(side="right", padx=4)

        # 主体：左右分栏
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=15, pady=10)

        # 左侧：报告类型 + 段落列表
        left = ctk.CTkFrame(body, width=220, corner_radius=10)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="报告类型", font=("微软雅黑", 13, "bold")).pack(pady=(15, 5))
        report_types = get_report_types(self.config)
        self.report_type_var = ctk.StringVar(value=report_types[0] if report_types else "")
        self.report_type_menu = ctk.CTkOptionMenu(
            left,
            values=report_types,
            variable=self.report_type_var,
            command=lambda _: self._refresh_paragraph_list(),
            width=180,
            font=("微软雅黑", 12),
        )
        self.report_type_menu.pack(pady=5, padx=15)

        ctk.CTkLabel(left, text="段落类型", font=("微软雅黑", 13, "bold")).pack(pady=(20, 5))
        self.paragraph_listbox_frame = ctk.CTkScrollableFrame(left, width=180, height=400)
        self.paragraph_listbox_frame.pack(fill="both", expand=True, padx=15, pady=5)
        self.paragraph_buttons: list = []
        self.current_paragraph: str | None = None

        # 右侧：字段编辑表单
        right = ctk.CTkFrame(body, corner_radius=10)
        right.pack(side="left", fill="both", expand=True)
        self.form_title = ctk.CTkLabel(
            right, text="（请在左侧选择段落）", font=("微软雅黑", 14, "bold")
        )
        self.form_title.pack(pady=(15, 10))
        self.form_frame = ctk.CTkScrollableFrame(right)
        self.form_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # 底部：状态栏
        self.status_bar = ctk.CTkLabel(
            self,
            text="就绪",
            font=("微软雅黑", 11),
            text_color="gray60",
            anchor="w",
        )
        self.status_bar.pack(fill="x", padx=15, pady=(0, 10))

    # ------------ 段落列表与表单 ------------
    def _refresh_paragraph_list(self) -> None:
        for btn in self.paragraph_buttons:
            btn.destroy()
        self.paragraph_buttons.clear()

        report_type = self.report_type_var.get()
        for name in get_paragraph_types(self.config, report_type):
            btn = ctk.CTkButton(
                self.paragraph_listbox_frame,
                text=name,
                anchor="w",
                font=("微软雅黑", 12),
                height=32,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._select_paragraph(n),
            )
            btn.pack(fill="x", pady=2)
            self.paragraph_buttons.append(btn)

        self.current_paragraph = None
        self._clear_form()

    def _select_paragraph(self, paragraph: str) -> None:
        if self.dirty and self.current_paragraph and self.current_paragraph != paragraph:
            self._collect_form_into_config()  # 切换前先把当前表单存回内存

        self.current_paragraph = paragraph
        for btn in self.paragraph_buttons:
            if btn.cget("text") == paragraph:
                btn.configure(fg_color=("gray75", "gray30"))
            else:
                btn.configure(fg_color="transparent")

        self._render_form()

    def _clear_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_widgets.clear()
        self.form_title.configure(text="（请在左侧选择段落）")

    def _render_form(self) -> None:
        self._clear_form()
        report_type = self.report_type_var.get()
        paragraph = self.current_paragraph
        if not paragraph:
            return

        section = self.config[report_type][paragraph]
        self.form_title.configure(text=f"{report_type} → {paragraph}")

        for key, label, kind, options in FIELD_SCHEMA:
            row = ctk.CTkFrame(self.form_frame, fg_color="transparent")
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(
                row,
                text=label,
                font=("微软雅黑", 12),
                width=180,
                anchor="w",
            ).pack(side="left", padx=(5, 10))

            value = section.get(key)
            widget = self._make_widget(row, key, kind, options, value)
            if widget is not None:
                widget.pack(side="left", fill="x", expand=True)

    def _make_widget(self, parent, key: str, kind: str, options, value):
        """根据字段类型创建对应控件，并把"取值器"塞进 self.field_widgets[key]。"""
        if kind == "text" or kind == "combo_text":
            var = ctk.StringVar(value=str(value) if value is not None else "")
            if kind == "combo_text" and options:
                widget = ctk.CTkComboBox(parent, values=list(options), variable=var, width=240)
            else:
                widget = ctk.CTkEntry(parent, textvariable=var, width=240)
            self.field_widgets[key] = ("text", var)
            return widget

        if kind == "float":
            var = ctk.StringVar(value=str(value) if value is not None else "0.0")
            widget = ctk.CTkEntry(parent, textvariable=var, width=240)
            self.field_widgets[key] = ("float", var)
            return widget

        if kind == "int":
            var = ctk.StringVar(value=str(value) if value is not None else "0")
            widget = ctk.CTkEntry(parent, textvariable=var, width=240)
            self.field_widgets[key] = ("int", var)
            return widget

        if kind == "bool":
            var = ctk.BooleanVar(value=bool(value) if value is not None else False)
            widget = ctk.CTkSwitch(parent, text="", variable=var, onvalue=True, offvalue=False)
            self.field_widgets[key] = ("bool", var)
            return widget

        if kind == "enum_int":
            label_to_int: dict[str, int] = {v: k for k, v in (options or {}).items()}
            current_label = (options or {}).get(
                value, list((options or {}).values())[0] if options else ""
            )
            var = ctk.StringVar(value=current_label)
            widget = ctk.CTkOptionMenu(
                parent, values=list((options or {}).values()), variable=var, width=240
            )
            self.field_widgets[key] = ("enum_int", (var, label_to_int))
            return widget

        return None

    def _collect_form_into_config(self) -> bool:
        """把当前表单的值收回到 self.config[report][paragraph]，返回是否成功。"""
        if not self.current_paragraph:
            return True
        report_type = self.report_type_var.get()
        section = self.config[report_type][self.current_paragraph]

        for key, kind_pair in self.field_widgets.items():
            kind, holder = kind_pair
            try:
                if kind == "text":
                    section[key] = holder.get()
                elif kind == "float":
                    section[key] = float(holder.get())
                elif kind == "int":
                    section[key] = int(holder.get())
                elif kind == "bool":
                    section[key] = bool(holder.get())
                elif kind == "enum_int":
                    var, mapping = holder
                    section[key] = mapping[var.get()]
            except (ValueError, KeyError) as e:
                messagebox.showerror("输入错误", f"字段 [{key}] 的值非法:\n{e}")
                return False

        self.dirty = True
        self._set_status(f"已暂存修改：{report_type} → {self.current_paragraph}")
        return True

    # ------------ 保存 / 重载 ------------
    def _save(self) -> None:
        if not self._collect_form_into_config():
            return
        try:
            save_config(self.config, self.config_path)
            self.dirty = False
            self._set_status(f"✅ 已保存到 {os.path.basename(self.config_path)}")
            messagebox.showinfo("保存成功", "配置已写回 JSON 文件。")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _reload(self) -> None:
        if self.dirty and not messagebox.askyesno("确认放弃修改", "有未保存的修改，确定重新加载？"):
            return
        try:
            self.config = load_config(self.config_path)
            self.dirty = False
            self._refresh_paragraph_list()
            self._set_status("🔄 已重新加载配置")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def _set_status(self, text: str) -> None:
        self.status_bar.configure(text=text)

    def request_close(self) -> bool:
        """让外层窗口在关闭前问"是否放弃未保存修改"。返回是否真的可关。"""
        if self.dirty and not messagebox.askyesno("确认退出", "有未保存的修改，确定退出？"):
            return False
        return True


class ConfigEditorApp:
    """独立窗口模式：把 ConfigEditorPanel 包在一个 CTk 窗口里。"""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._win = ctk.CTk()
        self._win.title(f"报告样式配置编辑器 - {os.path.basename(config_path)}")
        self._win.geometry("960x720")
        self.panel = ConfigEditorPanel(self._win, config_path=config_path)
        self.panel.pack(fill="both", expand=True)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self.panel.request_close():
            self._win.destroy()

    def run(self) -> None:
        self._win.mainloop()


def _main() -> None:
    enable_line_buffered_stdout()
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    ConfigEditorApp().run()


if __name__ == "__main__":
    _main()
