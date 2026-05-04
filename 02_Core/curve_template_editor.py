"""
曲线模板可视化编辑器 (curve_template_editor.py)

可视化编辑 04_Config/curve_templates.json：增/删/复制/重命名模板，
编辑各字段、坐标轴、每条曲线的点序列。

【强烈推荐】先在顶部"挂载参考 Excel"按钮挑一个目标 Excel —— 之后所有 var_column
字段会自动变成"从 Excel 实际表头里下拉选择"，避免手工输入引起的空白/全角差异。

业务函数（load_templates / save_templates / read_excel_columns）纯参数，可被复用。
"""

import json
import os
import sys
from copy import deepcopy
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk
from common.io_helpers import enable_line_buffered_stdout, read_sheet_names

DEFAULT_TEMPLATES_PATH = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "04_Config", "curve_templates.json")
)

# 给一些常用默认值，新模板/新曲线/新点直接套上即可
EMPTY_TEMPLATE: dict[str, Any] = {
    "id_column": "锚杆编号",
    "filename_template": "锚杆{id}_曲线.png",
    "title_template": "锚杆{id}：曲线",
    "x_axis": {"label": "位移 (mm)", "range": None},
    "y_axis": {"label": "荷载 (KN)", "range": [0, 200, 20]},
    "curves": [],
}
EMPTY_CURVE: dict[str, Any] = {
    "name": "曲线",
    "color": "#1F4FE0",
    "marker": "s",
    "linewidth": 2.0,
    "markersize": 7.0,
    "points": [],
}
EMPTY_POINT: dict[str, Any] = {
    "fixed_axis": "y",
    "fixed_value": 0.0,
    "var_column": "",
}

COMMON_COLORS = ["#1F4FE0", "#E03A3A", "#1AAA55", "#FFA500", "#9C27B0", "#000000"]
COMMON_MARKERS = ["s", "o", "^", "v", "D", "x", "*", "+"]


# ==========================================
# 模块 1：核心业务（纯函数）
# ==========================================
def load_templates(path: str = DEFAULT_TEMPLATES_PATH) -> dict[str, Any]:
    """读取模板库；文件不存在时返回空 dict（首次使用时不报错）。"""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_templates(templates: dict[str, Any], path: str = DEFAULT_TEMPLATES_PATH) -> None:
    """写回 JSON：utf-8 + 4 空格缩进 + 中文不转义。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=4)


def read_excel_columns(excel_path: str, sheet_name: str | None = None) -> list[str]:
    """读取指定 Sheet 的表头列名（已 strip）。"""
    import pandas as pd

    df = pd.read_excel(excel_path, sheet_name=sheet_name, nrows=0)
    return [str(c).strip() for c in df.columns]


# ==========================================
# 模块 2：UI 流程
# ==========================================
class CurveTemplateEditorPanel(ctk.CTkFrame):
    """曲线模板编辑器 —— CTkFrame，可被嵌入主控制台或独立窗口。"""

    def __init__(self, master, path: str = DEFAULT_TEMPLATES_PATH, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self.path = path
        self.templates: dict[str, Any] = load_templates(path)
        self.current_name: str | None = None
        self.dirty: bool = False
        self.excel_columns: list[str] = []  # 用户挂载 Excel 后填充

        self._build_layout()
        self._refresh_template_list()

    # ============== 布局 ==============
    def _build_layout(self) -> None:
        # 顶栏：路径 + Excel 挂载 + 保存
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(
            top, text=f"模板库：{self.path}", font=("微软雅黑", 11), text_color="gray50"
        ).pack(side="left")
        ctk.CTkButton(top, text="💾 保存", width=80, height=30, command=self._save).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            top,
            text="🔄 重新加载",
            width=90,
            height=30,
            fg_color="gray40",
            command=self._reload,
        ).pack(side="right", padx=4)

        # Excel 挂载条
        excel_bar = ctk.CTkFrame(self)
        excel_bar.pack(fill="x", padx=15, pady=5)
        ctk.CTkButton(
            excel_bar,
            text="📂 挂载参考 Excel（让列名变下拉选择）",
            command=self._mount_excel,
            width=300,
            height=30,
        ).pack(side="left", padx=10, pady=5)
        self.excel_status = ctk.CTkLabel(
            excel_bar,
            text="未挂载 - 列名需要手工输入",
            text_color="gray60",
            font=("微软雅黑", 11),
        )
        self.excel_status.pack(side="left", padx=10)

        # 主体：左右分栏
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=15, pady=10)

        # === 左侧：模板列表 ===
        left = ctk.CTkFrame(body, width=240, corner_radius=10)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="模板列表", font=("微软雅黑", 13, "bold")).pack(pady=(15, 5))
        self.template_listbox = ctk.CTkScrollableFrame(left, width=210, height=520)
        self.template_listbox.pack(fill="both", expand=True, padx=15)
        self._tpl_buttons: list[ctk.CTkButton] = []

        btn_bar = ctk.CTkFrame(left, fg_color="transparent")
        btn_bar.pack(fill="x", padx=15, pady=10)
        ctk.CTkButton(btn_bar, text="+ 新建", width=60, height=28, command=self._new_template).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            btn_bar,
            text="复制",
            width=60,
            height=28,
            command=self._duplicate_template,
            fg_color="gray45",
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_bar,
            text="删除",
            width=60,
            height=28,
            command=self._delete_template,
            fg_color="#aa3333",
        ).pack(side="left", padx=2)

        # === 右侧：表单 ===
        right = ctk.CTkFrame(body, corner_radius=10)
        right.pack(side="left", fill="both", expand=True)
        self.form_title = ctk.CTkLabel(
            right, text="（请在左侧选择或新建模板）", font=("微软雅黑", 14, "bold")
        )
        self.form_title.pack(pady=(15, 10))
        self.form_frame = ctk.CTkScrollableFrame(right)
        self.form_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # 状态栏
        self.status_bar = ctk.CTkLabel(
            self, text="就绪", font=("微软雅黑", 11), text_color="gray60", anchor="w"
        )
        self.status_bar.pack(fill="x", padx=15, pady=(0, 10))

    # ============== 模板列表 ==============
    def _refresh_template_list(self) -> None:
        for btn in self._tpl_buttons:
            btn.destroy()
        self._tpl_buttons.clear()

        names = [k for k in self.templates.keys() if not k.startswith("_")]
        for name in names:
            btn = ctk.CTkButton(
                self.template_listbox,
                text=name,
                anchor="w",
                font=("微软雅黑", 12),
                height=32,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._select_template(n),
            )
            btn.pack(fill="x", pady=2)
            self._tpl_buttons.append(btn)

        if names and (self.current_name not in names):
            self._select_template(names[0])
        elif self.current_name:
            self._select_template(self.current_name)
        else:
            self._clear_form()

    def _select_template(self, name: str) -> None:
        if name not in self.templates:
            return
        # 切换前不主动收集表单，因为表单上的修改是即时挂回 dict 的
        self.current_name = name
        for btn in self._tpl_buttons:
            btn.configure(
                fg_color=("gray75", "gray30") if btn.cget("text") == name else "transparent"
            )
        self._render_form()

    def _new_template(self) -> None:
        name = simpledialog.askstring(
            "新建模板", "请输入新模板名称：", parent=self.winfo_toplevel()
        )
        if not name:
            return
        if name in self.templates:
            messagebox.showerror("名称冲突", f"已存在模板 '{name}'")
            return
        self.templates[name] = deepcopy(EMPTY_TEMPLATE)
        self.current_name = name
        self.dirty = True
        self._refresh_template_list()
        self._set_status(f"已新建模板 '{name}'（记得保存）")

    def _duplicate_template(self) -> None:
        if not self.current_name:
            return
        name = simpledialog.askstring(
            "复制模板",
            f"基于 '{self.current_name}' 复制一份，新名称：",
            parent=self.winfo_toplevel(),
            initialvalue=f"{self.current_name}_副本",
        )
        if not name:
            return
        if name in self.templates:
            messagebox.showerror("名称冲突", f"已存在模板 '{name}'")
            return
        self.templates[name] = deepcopy(self.templates[self.current_name])
        self.current_name = name
        self.dirty = True
        self._refresh_template_list()
        self._set_status(f"已复制为 '{name}'（记得保存）")

    def _delete_template(self) -> None:
        if not self.current_name:
            return
        if not messagebox.askyesno("确认删除", f"确定删除模板 '{self.current_name}'？"):
            return
        del self.templates[self.current_name]
        self.current_name = None
        self.dirty = True
        self._refresh_template_list()

    # ============== 表单渲染 ==============
    def _clear_form(self) -> None:
        for w in self.form_frame.winfo_children():
            w.destroy()
        self.form_title.configure(text="（请在左侧选择或新建模板）")

    def _render_form(self) -> None:
        self._clear_form()
        if not self.current_name:
            return
        tpl = self.templates[self.current_name]
        self.form_title.configure(text=f"编辑：{self.current_name}")

        # === 基本信息 ===
        self._section_header("基本信息")
        self._text_field(tpl, "id_column", "标识列（命名用）:")
        self._text_field(tpl, "filename_template", "输出文件名模板:")
        self._text_field(tpl, "title_template", "图标题模板:")

        # === X 轴 ===
        self._section_header("X 轴")
        self._axis_subform(tpl["x_axis"])

        # === Y 轴 ===
        self._section_header("Y 轴")
        self._axis_subform(tpl["y_axis"])

        # === 曲线 ===
        self._section_header("曲线")
        for i, curve in enumerate(tpl["curves"]):
            self._curve_subform(tpl["curves"], i)

        ctk.CTkButton(
            self.form_frame,
            text="+ 添加曲线",
            height=32,
            command=lambda: self._add_curve(tpl),
        ).pack(fill="x", pady=8, padx=4)

    def _section_header(self, text: str) -> None:
        bar = ctk.CTkFrame(self.form_frame, fg_color="#0078d4", height=4)
        bar.pack(fill="x", pady=(15, 4))
        ctk.CTkLabel(self.form_frame, text=text, font=("微软雅黑", 13, "bold")).pack(anchor="w")

    def _row(self, parent=None) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent or self.form_frame, fg_color="transparent")
        row.pack(fill="x", pady=3)
        return row

    def _text_field(self, holder: dict[str, Any], key: str, label: str, parent=None) -> None:
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, font=("微软雅黑", 12), width=170, anchor="w").pack(
            side="left"
        )
        var = ctk.StringVar(value=str(holder.get(key, "")))
        entry = ctk.CTkEntry(row, textvariable=var, width=420)
        entry.pack(side="left", fill="x", expand=True)

        def _on_change(*_):
            holder[key] = var.get()
            self.dirty = True

        var.trace_add("write", _on_change)

    def _float_field(
        self, holder: dict[str, Any], key: str, label: str, parent=None, width: int = 120
    ) -> None:
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, font=("微软雅黑", 12), width=120, anchor="w").pack(
            side="left"
        )
        var = ctk.StringVar(value=str(holder.get(key, 0)))
        entry = ctk.CTkEntry(row, textvariable=var, width=width)
        entry.pack(side="left", padx=4)

        def _on_change(*_):
            try:
                holder[key] = float(var.get())
                self.dirty = True
            except ValueError:
                pass

        var.trace_add("write", _on_change)

    def _axis_subform(self, axis: dict[str, Any]) -> None:
        self._text_field(axis, "label", "轴标签:")

        row = self._row()
        ctk.CTkLabel(row, text="范围:", font=("微软雅黑", 12), width=170, anchor="w").pack(
            side="left"
        )

        use_range_var = ctk.BooleanVar(value=axis.get("range") is not None)
        switch = ctk.CTkSwitch(row, text="启用固定范围", variable=use_range_var)
        switch.pack(side="left")

        # range 输入框区
        range_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        range_frame.pack(fill="x")

        rng = axis.get("range") or [0.0, 1.0, 0.1]
        rng_holder = {"min": float(rng[0]), "max": float(rng[1]), "step": float(rng[2])}

        rrow = ctk.CTkFrame(range_frame, fg_color="transparent")
        rrow.pack(fill="x", pady=2)
        ctk.CTkLabel(rrow, text="", width=170).pack(side="left")
        for k in ("min", "max", "step"):
            ctk.CTkLabel(rrow, text=k, font=("微软雅黑", 11)).pack(side="left", padx=(8, 2))
            v = ctk.StringVar(value=str(rng_holder[k]))
            e = ctk.CTkEntry(rrow, textvariable=v, width=70)
            e.pack(side="left")

            def _make_setter(key=k, var=v):
                def _on(*_):
                    try:
                        rng_holder[key] = float(var.get())
                        if use_range_var.get():
                            axis["range"] = [
                                rng_holder["min"],
                                rng_holder["max"],
                                rng_holder["step"],
                            ]
                            self.dirty = True
                    except ValueError:
                        pass

                return _on

            v.trace_add("write", _make_setter())

        def _toggle(*_):
            if use_range_var.get():
                axis["range"] = [rng_holder["min"], rng_holder["max"], rng_holder["step"]]
            else:
                axis["range"] = None
            self.dirty = True

        use_range_var.trace_add("write", _toggle)

    def _curve_subform(self, curves: list[dict[str, Any]], idx: int) -> None:
        curve = curves[idx]
        wrap = ctk.CTkFrame(self.form_frame, corner_radius=8, fg_color=("gray92", "gray22"))
        wrap.pack(fill="x", pady=8, padx=2)

        # 标题栏：名称 + 删除
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text=f"曲线 #{idx + 1}", font=("微软雅黑", 12, "bold")).pack(side="left")
        ctk.CTkButton(
            top,
            text="× 删除曲线",
            width=90,
            height=24,
            fg_color="#aa3333",
            command=lambda: self._remove_curve(curves, idx),
        ).pack(side="right")

        # 基本字段
        body = ctk.CTkFrame(wrap, fg_color="transparent")
        body.pack(fill="x", padx=10, pady=4)
        self._text_field(curve, "name", "曲线名:", parent=body)

        # color 用 ComboBox
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="颜色 (hex):", font=("微软雅黑", 12), width=170, anchor="w").pack(
            side="left"
        )
        cv = ctk.StringVar(value=curve.get("color", "#1F4FE0"))
        cb = ctk.CTkComboBox(row, values=COMMON_COLORS, variable=cv, width=150)
        cb.pack(side="left", padx=4)

        def _set_color(*_):
            curve["color"] = cv.get()
            self.dirty = True

        cv.trace_add("write", _set_color)

        # marker 用 ComboBox
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(
            row, text="标记 (matplotlib):", font=("微软雅黑", 12), width=170, anchor="w"
        ).pack(side="left")
        mv = ctk.StringVar(value=curve.get("marker", "s"))
        mb = ctk.CTkComboBox(row, values=COMMON_MARKERS, variable=mv, width=80)
        mb.pack(side="left", padx=4)

        def _set_marker(*_):
            curve["marker"] = mv.get()
            self.dirty = True

        mv.trace_add("write", _set_marker)

        self._float_field(curve, "linewidth", "线宽:", parent=body, width=80)
        self._float_field(curve, "markersize", "标记尺寸:", parent=body, width=80)

        # 数据点列表
        pts_label = ctk.CTkLabel(
            body, text=f"数据点 ({len(curve['points'])} 个)", font=("微软雅黑", 12, "bold")
        )
        pts_label.pack(anchor="w", pady=(8, 4))

        for pidx, pt in enumerate(curve["points"]):
            self._point_subform(curve["points"], pidx, parent=body)

        ctk.CTkButton(
            body,
            text="+ 添加点",
            height=28,
            command=lambda: self._add_point(curve),
        ).pack(fill="x", pady=4)

    def _point_subform(self, points: list[dict[str, Any]], pidx: int, parent) -> None:
        pt = points[pidx]
        row = ctk.CTkFrame(parent, fg_color=("gray86", "gray26"), corner_radius=6)
        row.pack(fill="x", pady=2)

        ctk.CTkLabel(row, text=f"#{pidx + 1}", font=("微软雅黑", 11), width=30).pack(
            side="left", padx=(8, 4)
        )

        # fixed_axis 选 x/y
        ax_var = ctk.StringVar(value=pt.get("fixed_axis", "y"))
        ax_menu = ctk.CTkOptionMenu(row, values=["x", "y"], variable=ax_var, width=55)
        ax_menu.pack(side="left", padx=2)
        ctk.CTkLabel(row, text="=", font=("微软雅黑", 11)).pack(side="left")

        # fixed_value
        fv_var = ctk.StringVar(value=str(pt.get("fixed_value", 0)))
        fv_entry = ctk.CTkEntry(row, textvariable=fv_var, width=70)
        fv_entry.pack(side="left", padx=2)

        ctk.CTkLabel(row, text=", 另一轴 ←", font=("微软雅黑", 11)).pack(side="left", padx=(6, 2))

        # var_column：有 Excel 列时下拉，否则文本框
        if self.excel_columns:
            cv_var = ctk.StringVar(value=pt.get("var_column", ""))
            cv_widget = ctk.CTkComboBox(row, values=self.excel_columns, variable=cv_var, width=320)
        else:
            cv_var = ctk.StringVar(value=pt.get("var_column", ""))
            cv_widget = ctk.CTkEntry(row, textvariable=cv_var, width=320)
        cv_widget.pack(side="left", padx=2, fill="x", expand=True)

        # 删除按钮
        ctk.CTkButton(
            row,
            text="×",
            width=28,
            height=24,
            fg_color="#aa3333",
            command=lambda: self._remove_point(points, pidx),
        ).pack(side="right", padx=4)

        # 绑定回调
        def _save_axis(*_):
            pt["fixed_axis"] = ax_var.get()
            self.dirty = True

        ax_var.trace_add("write", _save_axis)

        def _save_value(*_):
            try:
                pt["fixed_value"] = float(fv_var.get())
                self.dirty = True
            except ValueError:
                pass

        fv_var.trace_add("write", _save_value)

        def _save_col(*_):
            pt["var_column"] = cv_var.get()
            self.dirty = True

        cv_var.trace_add("write", _save_col)

    # ============== 曲线/点 增删 ==============
    def _add_curve(self, tpl: dict[str, Any]) -> None:
        tpl["curves"].append(deepcopy(EMPTY_CURVE))
        self.dirty = True
        self._render_form()

    def _remove_curve(self, curves: list[dict[str, Any]], idx: int) -> None:
        if not messagebox.askyesno("确认", f"删除曲线 #{idx + 1}？"):
            return
        del curves[idx]
        self.dirty = True
        self._render_form()

    def _add_point(self, curve: dict[str, Any]) -> None:
        curve["points"].append(deepcopy(EMPTY_POINT))
        self.dirty = True
        self._render_form()

    def _remove_point(self, points: list[dict[str, Any]], idx: int) -> None:
        del points[idx]
        self.dirty = True
        self._render_form()

    # ============== Excel 挂载 ==============
    def _mount_excel(self) -> None:
        excel = filedialog.askopenfilename(
            title="选择参考 Excel（拿表头给列名做下拉）",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")],
        )
        if not excel:
            return
        sheets = read_sheet_names(excel)
        if not sheets:
            messagebox.showerror("Excel 无 Sheet", "无法读取该 Excel 的工作表。")
            return

        # 简化处理：直接让用户选哪个 Sheet
        if len(sheets) == 1:
            sheet = sheets[0]
        else:
            sheet = simpledialog.askstring(
                "选择工作表",
                f"可用 Sheet：{sheets}\n\n请输入要使用的 Sheet 名:",
                parent=self.winfo_toplevel(),
                initialvalue=sheets[0],
            )
            if sheet not in sheets:
                messagebox.showerror("Sheet 不存在", f"'{sheet}' 不在 {sheets} 中。")
                return

        try:
            self.excel_columns = read_excel_columns(excel, sheet)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        self.excel_status.configure(
            text=f"✅ {os.path.basename(excel)} / {sheet} - {len(self.excel_columns)} 列已挂载",
            text_color="green",
        )
        self._set_status("已挂载 Excel，列名将以下拉方式呈现")
        self._render_form()  # 重渲染让 var_column 字段变成 ComboBox

    # ============== 保存 / 重载 / 退出 ==============
    def _save(self) -> None:
        try:
            save_templates(self.templates, self.path)
            self.dirty = False
            self._set_status(f"✅ 已保存到 {os.path.basename(self.path)}")
            messagebox.showinfo("保存成功", "曲线模板已写回 JSON。")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _reload(self) -> None:
        if self.dirty and not messagebox.askyesno("确认放弃修改", "有未保存的修改，确定重新加载？"):
            return
        self.templates = load_templates(self.path)
        self.dirty = False
        self.current_name = None
        self._refresh_template_list()
        self._set_status("🔄 已重新加载")

    def _set_status(self, text: str) -> None:
        self.status_bar.configure(text=text)

    def request_close(self) -> bool:
        """让外层窗口关闭前问"是否放弃未保存"。返回是否真的可关。"""
        if self.dirty and not messagebox.askyesno("确认退出", "有未保存的修改，确定退出？"):
            return False
        return True


class CurveTemplateEditorApp:
    """独立窗口模式：把 CurveTemplateEditorPanel 包在一个 CTk 窗口里。"""

    def __init__(self, path: str = DEFAULT_TEMPLATES_PATH):
        self._win = ctk.CTk()
        self._win.title(f"曲线模板编辑器 - {os.path.basename(path)}")
        self._win.geometry("1100x780")
        self.panel = CurveTemplateEditorPanel(self._win, path=path)
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
    CurveTemplateEditorApp().run()


if __name__ == "__main__":
    _main()
