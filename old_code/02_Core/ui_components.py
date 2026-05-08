"""
===============================================================================
脚本名称：全局现代 UI 组件库 - 工业级防吞窗版 (ui_components.py)
功能概述：
    采用 Singleton (单例) 隐藏根窗口 + Toplevel 架构。
    彻底解决由于连续创建/销毁 CTk 实例导致的“弹窗被系统静默吞噬”或闪退 Bug。
===============================================================================
"""

import json
import os
import queue
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

# 全局基础设置
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# 【核心护城河】：全局唯一隐藏主窗口
_global_root = None


def _get_root():
    global _global_root
    if _global_root is None or not _global_root.winfo_exists():
        _global_root = ctk.CTk()
        _global_root.withdraw()  # 永远隐藏，仅做锚点
    return _global_root


class BaseDialog:
    """弹窗基类，处理居中和基础属性"""

    def __init__(self, title, width, height):
        # 【架构升级】：所有弹窗作为子窗口依附于隐藏的根窗口
        self.root = ctk.CTkToplevel(_get_root())
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")

        # 强制置顶与焦点获取，彻底防止弹窗被 Word 挡住或被吞掉
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.root.resizable(False, False)

        # 屏幕居中计算
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")


class ModernConfirmDialog(BaseDialog):
    """现代确认弹窗"""

    def __init__(self, title, message, sub_message=""):
        super().__init__(title, 500, 320)
        self.result = False

        self.frame = ctk.CTkFrame(self.root, corner_radius=10)
        self.frame.pack(fill="both", expand=True, padx=25, pady=(25, 10))

        self.lbl_msg = ctk.CTkLabel(
            self.frame, text=message, font=("微软雅黑", 14, "bold"), justify="center"
        )
        self.lbl_msg.pack(pady=(25, 5), padx=20)

        if sub_message:
            self.lbl_sub = ctk.CTkLabel(
                self.frame,
                text=sub_message,
                font=("微软雅黑", 12),
                text_color="gray60",
                justify="center",
            )
            self.lbl_sub.pack(pady=10, padx=20)

        self.btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.btn_frame.pack(pady=25)

        self.btn_confirm = ctk.CTkButton(
            self.btn_frame,
            text="确定执行",
            font=("微软雅黑", 13, "bold"),
            width=160,
            height=45,
            command=self._confirm,
        )
        self.btn_confirm.pack(side="left", padx=10)

        self.btn_cancel = ctk.CTkButton(
            self.btn_frame,
            text="取消",
            font=("微软雅黑", 13),
            width=120,
            height=45,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._cancel,
        )
        self.btn_cancel.pack(side="left", padx=10)

    def _confirm(self):
        self.result = True
        self.root.destroy()

    def _cancel(self):
        self.result = False
        self.root.destroy()

    def show(self):
        # 模态阻塞：接管底层事件队列，防止主程序提前偷跑
        self.root.grab_set()
        self.root.master.wait_window(self.root)
        return self.result


class ModernProgressConsole(BaseDialog):
    """现代进度控制台 (多线程队列安全版)"""

    def __init__(self, title, max_val):
        super().__init__(title, 420, 220)
        self.is_cancelled = False
        self.max_val = max_val

        # 【核心护城河】：跨线程信箱
        self.msg_queue = queue.Queue()

        self.lbl_title = ctk.CTkLabel(
            self.root, text="引擎运行中...", font=("微软雅黑", 16, "bold")
        )
        self.lbl_title.pack(pady=(25, 5))

        self.lbl_status = ctk.CTkLabel(
            self.root, text="初始化...", font=("Consolas", 11), text_color="gray60"
        )
        self.lbl_status.pack()

        self.bar = ctk.CTkProgressBar(self.root, width=340, height=12, corner_radius=6)
        self.bar.pack(pady=20)
        self.bar.set(0)

        self.btn_stop = ctk.CTkButton(
            self.root,
            text="紧急停止",
            font=("微软雅黑", 12, "bold"),
            fg_color="#d32f2f",
            hover_color="#b71c1c",
            width=140,
            height=40,
            command=self._stop,
        )
        self.btn_stop.pack(pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self._stop)

        # 启动主线程的“雷达”
        self._poll_queue()

    def _poll_queue(self):
        """主线程的雷达：每 50 毫秒去信箱看一眼有没有人递纸条"""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg["type"] == "progress":
                    progress_ratio = msg["val"] / self.max_val if self.max_val > 0 else 0
                    self.bar.set(progress_ratio)
                    self.lbl_status.configure(text=msg["text"])
                elif msg["type"] == "close":
                    if self.root.winfo_exists():
                        self.root.destroy()
                    return  # 收到销毁指令，雷达关机
        except queue.Empty:
            pass

        # 只要窗口还活着，就继续设个闹钟过 50 毫秒再来检查
        if self.root.winfo_exists():
            self.root.after(50, self._poll_queue)

    def update_progress(self, current_val, status_text):
        """【后台专供】：绝对不碰 UI，只往信箱里扔纸条"""
        self.msg_queue.put({"type": "progress", "val": current_val, "text": status_text})

    def _stop(self):
        self.is_cancelled = True
        self.lbl_status.configure(text="正在中止安全环境...", text_color="#d32f2f")
        self.btn_stop.configure(state="disabled")

    def close(self):
        """【后台专供】：递交关窗纸条"""
        self.msg_queue.put({"type": "close"})


class ModernInfoDialog(BaseDialog):
    """现代信息反馈弹窗"""

    def __init__(self, title, message):
        super().__init__(title, 550, 420)

        self.frame = ctk.CTkFrame(self.root, corner_radius=10)
        self.frame.pack(fill="both", expand=True, padx=25, pady=25)

        inner_content = ctk.CTkFrame(self.frame, fg_color="transparent")
        inner_content.pack(expand=True)

        self.lbl_msg = ctk.CTkLabel(
            inner_content, text=message, font=("微软雅黑", 13), justify="left"
        )
        self.lbl_msg.pack(pady=20, padx=20)

        self.btn_close = ctk.CTkButton(
            self.root,
            text="确定",
            font=("微软雅黑", 14, "bold"),
            width=180,
            height=48,
            command=self.root.destroy,
        )
        self.btn_close.pack(pady=(0, 25))

    def show(self):
        self.root.grab_set()
        self.root.master.wait_window(self.root)


class ModernParamDialog(BaseDialog):
    """现代参数输入面板"""

    def __init__(self, title, file_name, show_width=False):
        super().__init__(title, 500, 380 if show_width else 340)
        self.params = None

        ctk.CTkLabel(
            self.root, text=f"📄 目标文件: {file_name}", font=("微软雅黑", 13, "bold")
        ).pack(pady=(25, 15))

        # 必须绑定 master=self.root，防止变量脱离作用域
        self.type_var = ctk.StringVar(master=self.root, value="检测报告")

        # ---------------- 核心排版：Grid 网格布局 ----------------
        form_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        form_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # 配置列权重：左右两列为弹簧列拉伸，中间两列被强制居中对齐
        form_frame.grid_columnconfigure(0, weight=1)
        form_frame.grid_columnconfigure(1, weight=0, minsize=100)
        form_frame.grid_columnconfigure(2, weight=0, minsize=220)
        form_frame.grid_columnconfigure(3, weight=1)

        row_idx = 0

        # 第一行：报告类型
        ctk.CTkLabel(form_frame, text="报告类型:", font=("微软雅黑", 12)).grid(
            row=row_idx, column=1, sticky="e", pady=12, padx=(0, 15)
        )
        radio_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        radio_frame.grid(row=row_idx, column=2, sticky="w", pady=12)
        ctk.CTkRadioButton(
            radio_frame, text="检测报告", variable=self.type_var, value="检测报告"
        ).pack(side="left", padx=(0, 15))
        ctk.CTkRadioButton(
            radio_frame, text="鉴定报告", variable=self.type_var, value="鉴定报告"
        ).pack(side="left")
        row_idx += 1

        # 第二行：表格宽度（按需渲染）
        self.width_entry = None
        if show_width:
            # 【核心修改 1】：文案剥离，强行缩减为4个字，与上下保持绝对物理等长
            ctk.CTkLabel(form_frame, text="表格宽度:", font=("微软雅黑", 12)).grid(
                row=row_idx, column=1, sticky="e", pady=12, padx=(0, 15)
            )

            # 【核心修改 2】：创建一个内部小容器，用来横向包裹“输入框”和“%”符号
            width_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
            width_frame.grid(row=row_idx, column=2, sticky="w", pady=12)

            # 输入框长度稍微缩短至 195，给后面的 % 腾出视觉空间，保证整体 220 的总宽度
            self.width_entry = ctk.CTkEntry(width_frame, width=195)
            self.width_entry.insert(0, "95")
            self.width_entry.pack(side="left")

            # 【核心修改 3】：把 % 作为后缀单位，贴在输入框的右侧
            ctk.CTkLabel(width_frame, text="%", font=("微软雅黑", 12)).pack(
                side="left", padx=(5, 0)
            )
            row_idx += 1

        # 第三行：跳过页码
        ctk.CTkLabel(form_frame, text="跳过页码:", font=("微软雅黑", 12)).grid(
            row=row_idx, column=1, sticky="e", pady=12, padx=(0, 15)
        )
        self.skip_entry = ctk.CTkEntry(
            form_frame, placeholder_text="如: 1,2,3 (留空全排)", width=220
        )
        self.skip_entry.insert(0, "1,2,3,4")
        self.skip_entry.grid(row=row_idx, column=2, sticky="w", pady=12)
        # --------------------------------------------------------

        self.btn_confirm = ctk.CTkButton(
            self.root,
            text="确定",
            command=self._confirm,
            font=("微软雅黑", 14, "bold"),
            width=180,
            height=48,
        )
        self.btn_confirm.pack(pady=(20, 30))

    def _confirm(self):
        skips = []
        if self.skip_entry.get().strip():
            skips = [
                int(p.strip())
                for p in self.skip_entry.get().replace("，", ",").split(",")
                if p.strip().isdigit()
            ]

        self.params = {"report_type": self.type_var.get(), "skip_pages": skips}
        if self.width_entry:
            self.params["width"] = int(self.width_entry.get() or "100")
        self.root.destroy()

    def show(self):
        self.root.grab_set()
        self.root.master.wait_window(self.root)
        return self.params


class ModernHandwriteDialog(BaseDialog):
    """现代仿生手写生成器主控面板"""

    def __init__(self, title="仿生手写配置台"):
        # 弹窗尺寸需要比普通参数面板大，因为配置项很多
        super().__init__(title, 750, 800)
        self.config_data = None  # 用于存储最终点击“下一步”时返回的数据

        # 配置文件保存路径（存放在代码同级目录）
        self.config_file = "handwrite_config.json"

        # 【核心变量绑定】：必须绑定 master=self.root，防止变量脱离作用域导致报错或数据不更新
        self.var_excel_path = ctk.StringVar(master=self.root)
        self.var_json_path = ctk.StringVar(master=self.root)
        self.var_img_path = ctk.StringVar(master=self.root)
        self.var_font_dir = ctk.StringVar(master=self.root)
        self.var_output_dir = ctk.StringVar(master=self.root)

        self.var_sheet_name = ctk.StringVar(master=self.root, value="Sheet2")
        self.var_font_scale = ctk.DoubleVar(master=self.root, value=1.68)
        self.var_y_offset = ctk.DoubleVar(master=self.root, value=-1.5)
        self.var_spacing = ctk.IntVar(master=self.root, value=-5)

        self._build_ui()
        self.load_config()  # 启动时自动读取上次配置

    def _build_ui(self):
        """构建界面的总指挥"""
        # ================= 板块 1：文件与路径配置 =================
        frame_files = ctk.CTkFrame(self.root, corner_radius=10)
        frame_files.pack(pady=15, padx=20, fill="x")

        ctk.CTkLabel(frame_files, text="📂 核心文件配置", font=("微软雅黑", 15, "bold")).pack(
            pady=(15, 5)
        )

        self._add_file_selector(
            frame_files,
            "Excel 数据源:",
            self.var_excel_path,
            file_types=[("Excel", "*.xlsx *.xlsm")],
        )
        self._add_file_selector(
            frame_files, "JSON 坐标库:", self.var_json_path, file_types=[("JSON", "*.json")]
        )
        self._add_file_selector(
            frame_files, "空白底图文件:", self.var_img_path, file_types=[("图片", "*.png *.jpg")]
        )
        self._add_dir_selector(frame_files, "手写字体目录:", self.var_font_dir)
        self._add_dir_selector(frame_files, "PDF 输出目录:", self.var_output_dir)

        # ================= 板块 2：全局视觉参数 =================
        frame_params = ctk.CTkFrame(self.root, corner_radius=10)
        frame_params.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(frame_params, text="🎨 全局视觉微调", font=("微软雅黑", 15, "bold")).pack(
            pady=(15, 5)
        )

        self._add_entry_row(frame_params, "目标 Sheet 名称:", self.var_sheet_name)
        self._add_slider_row(frame_params, "全局字号缩放 (倍):", self.var_font_scale, 1.0, 2.5)
        self._add_slider_row(frame_params, "纵向偏移补偿 (px):", self.var_y_offset, -15.0, 15.0)
        self._add_slider_row(frame_params, "字距收缩程度:", self.var_spacing, -15, 5, is_int=True)

        # ================= 板块 3：状态管理与执行 =================
        frame_actions = ctk.CTkFrame(self.root, fg_color="transparent")
        frame_actions.pack(pady=20, fill="x")

        btn_save = ctk.CTkButton(
            frame_actions, text="💾 保存参数配置", width=140, command=self.save_config
        )
        btn_save.pack(side="left", padx=(40, 10))

        btn_load = ctk.CTkButton(
            frame_actions,
            text="🔄 重新加载配置",
            width=140,
            fg_color="#F39C12",
            hover_color="#D68910",
            command=self.load_config,
        )
        btn_load.pack(side="left", padx=10)

        # 第一阶段的终点，点击进入第二阶段（返回收集到的数据）
        btn_next = ctk.CTkButton(
            frame_actions,
            text="下一步：配置数据映射 ➡️",
            width=180,
            fg_color="#27AE60",
            hover_color="#1E8449",
            command=self._confirm,
        )
        btn_next.pack(side="right", padx=(10, 40))

    # ---------------- 辅助构建方法 ----------------
    def _add_file_selector(self, parent, label_text, string_var, file_types):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6, padx=15)
        ctk.CTkLabel(row, text=label_text, width=110, anchor="e", font=("微软雅黑", 12)).pack(
            side="left", padx=(0, 10)
        )
        entry = ctk.CTkEntry(row, textvariable=string_var, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        btn = ctk.CTkButton(
            row, text="浏览", width=60, command=lambda: self._browse_file(string_var, file_types)
        )
        btn.pack(side="right")

    def _add_dir_selector(self, parent, label_text, string_var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6, padx=15)
        ctk.CTkLabel(row, text=label_text, width=110, anchor="e", font=("微软雅黑", 12)).pack(
            side="left", padx=(0, 10)
        )
        entry = ctk.CTkEntry(row, textvariable=string_var, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        btn = ctk.CTkButton(
            row, text="选择", width=60, command=lambda: self._browse_dir(string_var)
        )
        btn.pack(side="right")

    def _add_entry_row(self, parent, label_text, string_var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=8, padx=15)
        ctk.CTkLabel(row, text=label_text, width=120, anchor="e", font=("微软雅黑", 12)).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkEntry(row, textvariable=string_var, width=150).pack(side="left")

    def _add_slider_row(self, parent, label_text, var, min_val, max_val, is_int=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=8, padx=15)
        ctk.CTkLabel(row, text=label_text, width=120, anchor="e", font=("微软雅黑", 12)).pack(
            side="left", padx=(0, 10)
        )
        val_label = ctk.CTkLabel(row, text=str(var.get()), width=40)
        val_label.pack(side="right", padx=(10, 0))

        def slider_callback(value):
            final_val = int(value) if is_int else round(value, 2)
            var.set(final_val)
            val_label.configure(text=str(final_val))

        slider = ctk.CTkSlider(
            row, from_=min_val, to=max_val, variable=var, command=slider_callback
        )
        slider.pack(side="left", fill="x", expand=True)

    # ---------------- 业务逻辑方法 ----------------
    def _browse_file(self, string_var, file_types):
        # 注意：这里需要确保弹出的系统文件框依然在顶层
        self.root.attributes("-topmost", False)
        path = filedialog.askopenfilename(filetypes=file_types)
        self.root.attributes("-topmost", True)
        if path:
            string_var.set(path)

    def _browse_dir(self, string_var):
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory()
        self.root.attributes("-topmost", True)
        if path:
            string_var.set(path)

    def save_config(self):
        config = {
            "excel_path": self.var_excel_path.get(),
            "json_path": self.var_json_path.get(),
            "img_path": self.var_img_path.get(),
            "font_dir": self.var_font_dir.get(),
            "output_dir": self.var_output_dir.get(),
            "sheet_name": self.var_sheet_name.get(),
            "font_scale": self.var_font_scale.get(),
            "y_offset": self.var_y_offset.get(),
            "spacing": self.var_spacing.get(),
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print("配置已保存！")  # 后续这里可以接你现成的 ModernInfoDialog
        except Exception as e:
            print(f"保存失败: {e}")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    config = json.load(f)
                self.var_excel_path.set(config.get("excel_path", ""))
                self.var_json_path.set(config.get("json_path", ""))
                self.var_img_path.set(config.get("img_path", ""))
                self.var_font_dir.set(config.get("font_dir", ""))
                self.var_output_dir.set(config.get("output_dir", ""))
                self.var_sheet_name.set(config.get("sheet_name", "Sheet2"))
                self.var_font_scale.set(config.get("font_scale", 1.68))
                self.var_y_offset.set(config.get("y_offset", -1.5))
                self.var_spacing.set(config.get("spacing", -5))
            except Exception:
                pass

    def _confirm(self):
        """点击下一步时，收集所有参数并销毁当前弹窗"""
        # 前置校验：必须选择 JSON，因为下一步严重依赖它
        if not self.var_json_path.get() or not os.path.exists(self.var_json_path.get()):
            # 可以在这里调出你的 ModernInfoDialog 提示用户
            return

        # 把所有数据打包成字典
        self.config_data = {
            "excel_path": self.var_excel_path.get(),
            "json_path": self.var_json_path.get(),
            "img_path": self.var_img_path.get(),
            "font_dir": self.var_font_dir.get(),
            "output_dir": self.var_output_dir.get(),
            "sheet_name": self.var_sheet_name.get(),
            "font_scale": self.var_font_scale.get(),
            "y_offset": self.var_y_offset.get(),
            "spacing": self.var_spacing.get(),
        }
        self.root.destroy()

    def show(self):
        """显示弹窗并阻塞，直到点击下一步被销毁"""
        self.root.grab_set()
        self.root.master.wait_window(self.root)
        return self.config_data  # 返回收集到的数据字典


class ModernMappingDialog(BaseDialog):
    """现代动态数据映射网络面板"""

    def __init__(self, json_path, title="动态阵列与数据映射配置"):
        super().__init__(title, 700, 600)
        self.mapping_data = None
        self.json_path = json_path

        # 1. 解析 JSON 获取所有的框选名称
        self.json_keys = self._parse_json_keys()
        # 下拉菜单选项：加上“无”选项
        self.combo_options = ["无"] + self.json_keys

        # 2. 核心阵列变量绑定
        self.var_cols = ctk.StringVar(master=self.root, value="2")  # 列数
        self.var_rows = ctk.StringVar(master=self.root, value="4")  # 行数
        self.var_excel_step = ctk.StringVar(master=self.root, value="4")  # 单组数据在Excel占几行

        self.var_x_base = ctk.StringVar(
            master=self.root, value="构件名称" if "构件名称" in self.json_keys else "无"
        )
        self.var_x_target = ctk.StringVar(
            master=self.root, value="右" if "右" in self.json_keys else "无"
        )

        self.var_y_base = ctk.StringVar(
            master=self.root, value="构件名称" if "构件名称" in self.json_keys else "无"
        )
        self.var_y_target = ctk.StringVar(
            master=self.root, value="下" if "下" in self.json_keys else "无"
        )

        # 用于存储动态生成的 Excel 坐标输入框变量
        self.coord_vars = {}

        if not self.json_keys:
            self._show_error("JSON 解析失败或文件为空！")
            return

        self._build_ui()
        self._update_total_count()  # 初始化计算总组数

    def _parse_json_keys(self):
        """读取 JSON 文件，提取所有顶层键名"""
        try:
            with open(self.json_path, encoding="utf-8") as f:
                data = json.load(f)
            return list(data.keys())
        except Exception as e:
            print(f"读取 JSON 失败: {e}")
            return []

    def _build_ui(self):
        # 使用 ScrollableFrame 防止 JSON 框太多导致屏幕放不下
        main_scroll = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ================= 板块 A：网格阵列引擎 =================
        frame_grid = ctk.CTkFrame(main_scroll, corner_radius=10)
        frame_grid.pack(pady=10, padx=10, fill="x")

        ctk.CTkLabel(
            frame_grid, text="📐 物理排版阵列 (自动计算步长)", font=("微软雅黑", 15, "bold")
        ).pack(pady=(15, 10))

        # 阵列行列设置
        row1 = ctk.CTkFrame(frame_grid, fg_color="transparent")
        row1.pack(fill="x", pady=5, padx=15)

        ctk.CTkLabel(row1, text="排版列数:", font=("微软雅黑", 12)).pack(side="left", padx=(0, 5))
        cb_cols = ctk.CTkComboBox(
            row1,
            values=["1", "2", "3", "4", "5", "6"],
            variable=self.var_cols,
            width=80,
            command=self._update_total_count,
        )
        cb_cols.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(row1, text="排版行数:", font=("微软雅黑", 12)).pack(side="left", padx=(0, 5))
        cb_rows = ctk.CTkComboBox(
            row1,
            values=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            variable=self.var_rows,
            width=80,
            command=self._update_total_count,
        )
        cb_rows.pack(side="left", padx=(0, 20))

        # 动态显示总组数
        self.lbl_total = ctk.CTkLabel(
            row1, text="单页总计: 8 组", font=("微软雅黑", 12, "bold"), text_color="#E67E22"
        )
        self.lbl_total.pack(side="right", padx=10)

        # 步长参照设置
        row2 = ctk.CTkFrame(frame_grid, fg_color="transparent")
        row2.pack(fill="x", pady=10, padx=15)

        ctk.CTkLabel(row2, text="横向(X)步长：从", font=("微软雅黑", 12)).pack(side="left")
        ctk.CTkComboBox(row2, values=self.combo_options, variable=self.var_x_base, width=120).pack(
            side="left", padx=5
        )
        ctk.CTkLabel(row2, text="测量至", font=("微软雅黑", 12)).pack(side="left")
        ctk.CTkComboBox(
            row2, values=self.combo_options, variable=self.var_x_target, width=120
        ).pack(side="left", padx=5)

        row3 = ctk.CTkFrame(frame_grid, fg_color="transparent")
        row3.pack(fill="x", pady=5, padx=15)

        ctk.CTkLabel(row3, text="纵向(Y)步长：从", font=("微软雅黑", 12)).pack(side="left")
        ctk.CTkComboBox(row3, values=self.combo_options, variable=self.var_y_base, width=120).pack(
            side="left", padx=5
        )
        ctk.CTkLabel(row3, text="测量至", font=("微软雅黑", 12)).pack(side="left")
        ctk.CTkComboBox(
            row3, values=self.combo_options, variable=self.var_y_target, width=120
        ).pack(side="left", padx=5)

        # ================= 板块 B：数据源连线 =================
        frame_data = ctk.CTkFrame(main_scroll, corner_radius=10)
        frame_data.pack(pady=10, padx=10, fill="x")

        ctk.CTkLabel(
            frame_data, text="🔗 Excel 数据映射 (留空则不写入)", font=("微软雅黑", 15, "bold")
        ).pack(pady=(15, 5))

        row_excel = ctk.CTkFrame(frame_data, fg_color="transparent")
        row_excel.pack(fill="x", pady=(0, 15), padx=15)
        ctk.CTkLabel(row_excel, text="单组数据在 Excel 中占用行数:", font=("微软雅黑", 12)).pack(
            side="left"
        )
        ctk.CTkEntry(row_excel, textvariable=self.var_excel_step, width=80).pack(
            side="left", padx=10
        )

        # 【核心魔法】：遍历 JSON 键名，动态生成输入框
        for key in self.json_keys:
            row_mapping = ctk.CTkFrame(frame_data, fg_color="transparent")
            row_mapping.pack(fill="x", pady=5, padx=30)

            ctk.CTkLabel(
                row_mapping,
                text=f"[{key}] 对应 Excel 坐标:",
                font=("微软雅黑", 12),
                width=180,
                anchor="e",
            ).pack(side="left", padx=(0, 10))

            var_coord = ctk.StringVar(master=self.root)
            self.coord_vars[key] = var_coord  # 存入字典备用

            # 给常见字段预设一点占位符提示，防止懵逼
            placeholder = ""
            if key == "构件名称":
                placeholder = "如: A1"
            elif "测点" in key:
                placeholder = "如: C1"

            entry = ctk.CTkEntry(
                row_mapping, textvariable=var_coord, placeholder_text=placeholder, width=150
            )
            entry.pack(side="left")

        # ================= 底部按钮 =================
        btn_confirm = ctk.CTkButton(
            self.root,
            text="🚀 启动引擎开始生成",
            font=("微软雅黑", 14, "bold"),
            width=200,
            height=45,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            command=self._confirm,
        )
        btn_confirm.pack(pady=20)

    def _update_total_count(self, *args):
        """实时计算组数：列数 x 行数"""
        try:
            cols = int(self.var_cols.get())
            rows = int(self.var_rows.get())
            total = cols * rows
            self.lbl_total.configure(text=f"单页总计: {total} 组")
        except ValueError:
            pass

    def _show_error(self, msg):
        ctk.CTkLabel(self.root, text=f"❌ {msg}", text_color="red", font=("微软雅黑", 14)).pack(
            pady=50
        )

    def _confirm(self):
        """收集所有映射数据并关闭窗口"""
        mapping = {}
        for key, var in self.coord_vars.items():
            coord = var.get().strip().upper()  # 自动转大写，比如 a1 变成 A1
            if coord:  # 只有填了坐标的才会被记录
                mapping[key] = coord

        self.mapping_data = {
            "grid_cols": int(self.var_cols.get()),
            "grid_rows": int(self.var_rows.get()),
            "excel_step": int(self.var_excel_step.get()),
            "x_base": self.var_x_base.get(),
            "x_target": self.var_x_target.get(),
            "y_base": self.var_y_base.get(),
            "y_target": self.var_y_target.get(),
            "coordinates": mapping,
        }
        self.root.destroy()

    def show(self):
        self.root.grab_set()
        self.root.master.wait_window(self.root)
        return self.mapping_data


class ModernDynamicFormDialog(BaseDialog):
    """
    通用动态表单生成器 (极度解耦版)
    功能：通过传入配置列表，自动生成各类输入控件，彻底消灭为不同业务写死 UI 的情况。
    """

    def __init__(self, title: str, form_schema: list[dict[str, Any]], width: int = 550):
        # 根据表单字段数量动态计算高度，每个字段约占 45px 高度，加上下边距和按钮空间
        calc_height = len(form_schema) * 45 + 150
        super().__init__(title, width, calc_height)

        self.form_schema = form_schema
        # 核心数据字典：用于存储所有控件绑定的 Variable 对象，键为字段的 key
        self.result_vars = {}
        # 最终点击确定后返回的数据集
        self.final_data: dict[str, Any] = {}

        # 整体采用可滚动的容器，防止字段过多超出屏幕范围
        self.scroll_frame = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(15, 5))

        # 动态渲染 UI 引擎
        self._build_dynamic_form()

        # 底部操作区
        self.btn_confirm = ctk.CTkButton(
            self.root,
            text="确定",
            command=self._confirm,
            font=("微软雅黑", 14, "bold"),
            width=180,
            height=45,
        )
        self.btn_confirm.pack(pady=(10, 20))

    def _build_dynamic_form(self):
        """遍历 Schema，按类型渲染对应的控件"""
        for item in self.form_schema:
            field_key = item.get("key")  # 提取数据的字典键，必填
            field_label = str(item.get("label", "") or "")  # 左侧显示的文字，必填
            field_type = item.get("type", "text")  # 控件类型，默认为单行文本
            default_val = item.get("default", "")  # 默认值

            # 创建单行容器
            row_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=8)

            # 统一左侧 Label 宽度，保证对齐整洁
            ctk.CTkLabel(
                row_frame, text=field_label, font=("微软雅黑", 12), width=120, anchor="e"
            ).pack(side="left", padx=(0, 15))

            # 【路由分发】：根据不同的 type 生成不同的控件
            if field_type == "text":
                var = ctk.StringVar(master=self.root, value=str(default_val))
                entry = ctk.CTkEntry(row_frame, textvariable=var, width=250)
                entry.pack(side="left")
                self.result_vars[field_key] = var

            elif field_type == "number":
                # 数字输入框，限制只能输入数字（这里用普通文本框+后续取值转换）
                var = ctk.StringVar(master=self.root, value=str(default_val))
                entry = ctk.CTkEntry(row_frame, textvariable=var, width=120)
                entry.pack(side="left")
                ctk.CTkLabel(row_frame, text=item.get("unit", ""), font=("微软雅黑", 12)).pack(
                    side="left", padx=(5, 0)
                )
                self.result_vars[field_key] = var

            elif field_type == "radio":
                var = ctk.StringVar(master=self.root, value=str(default_val))
                options = item.get("options", [])
                for opt in options:
                    ctk.CTkRadioButton(row_frame, text=opt, variable=var, value=opt).pack(
                        side="left", padx=(0, 15)
                    )
                self.result_vars[field_key] = var

            elif field_type == "select":
                # 下拉选择框，需要传入 options 列表
                options = [str(o) for o in item.get("options", [])]
                init_val = (
                    str(default_val)
                    if str(default_val) in options
                    else (options[0] if options else "")
                )
                var = ctk.StringVar(master=self.root, value=init_val)
                combo = ctk.CTkComboBox(
                    row_frame, values=options, variable=var, width=250, state="readonly"
                )
                combo.pack(side="left")
                self.result_vars[field_key] = var

            elif field_type == "file" or field_type == "dir":
                # 文件或目录选择器组合
                var = ctk.StringVar(master=self.root, value=str(default_val))
                entry = ctk.CTkEntry(row_frame, textvariable=var, state="readonly")
                entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

                # 绑定对应的点击事件
                if field_type == "file":
                    file_types = item.get("file_types", [("所有文件", "*.*")])
                    btn = ctk.CTkButton(
                        row_frame,
                        text="浏览",
                        width=60,
                        command=lambda v=var, ft=file_types: self._browse_file(v, ft),
                    )
                else:
                    btn = ctk.CTkButton(
                        row_frame,
                        text="选择目录",
                        width=60,
                        command=lambda v=var: self._browse_dir(v),
                    )
                btn.pack(side="right")
                self.result_vars[field_key] = var

    def _browse_file(self, var: ctk.StringVar, file_types: list):
        """文件选择路由（解除置顶防止文件框被挡住）"""
        self.root.attributes("-topmost", False)
        path = filedialog.askopenfilename(filetypes=file_types)
        self.root.attributes("-topmost", True)
        if path:
            var.set(path)

    def _browse_dir(self, var: ctk.StringVar):
        """目录选择路由"""
        self.root.attributes("-topmost", False)
        path = filedialog.askdirectory()
        self.root.attributes("-topmost", True)
        if path:
            var.set(path)

    def _confirm(self):
        """收集所有绑定变量的数据并打包成标准字典"""
        self.final_data = {}
        for key, var in self.result_vars.items():
            self.final_data[key] = var.get()
        self.root.destroy()

    def show(self) -> dict:
        """阻塞式调用，返回清洗后的数据字典"""
        self.root.grab_set()
        self.root.master.wait_window(self.root)
        return self.final_data
