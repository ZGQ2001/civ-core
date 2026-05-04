"""
工程自动化主控制台 (main.py) - V3

按工作流分组的左侧导航，右侧根据工具类型分两种呈现方式：

  ① 配置类工具（不需要附着 Word，纯 Python UI）：
     直接把 Panel 嵌入主窗口右侧 —— 改完保存就行，无需切窗口、无需 subprocess。
     当前已嵌入：报告样式配置 / 曲线模板编辑器

  ② 业务类工具（需要 COM 附着 Word/WPS、或者有自己的复杂多对话框流程）：
     仍以子进程方式启动，但 stdout 实时流到下方日志面板，避免"黑箱"。
     启动 / 停止 / 清空日志 都在主窗口里完成。

无论哪种方式，左侧导航始终可见，用户随时可以切换查看说明 / 切到配置编辑器修配置。
"""

import os
import queue
import subprocess
import sys
import threading

import customtkinter as ctk

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.help_tooltip import attach_help

# ============================================================
# 工具菜单 —— 按工作流分组
# 每个工具：(显示名, 标识符, 简介, 启动方式)
# 启动方式: ("subprocess", "脚本文件名.py")  或  ("embed", "面板工厂函数路径")
# ============================================================
ToolEntry = tuple[str, str, str, tuple[str, str]]

WORKFLOW_GROUPS: list[tuple[str, list[ToolEntry]]] = [
    (
        "📊 数据 / 图表",
        [
            (
                "批量绘图（Excel→PNG）",
                "plot_curves",
                "把 Excel 一个 Sheet 的每一行套用模板批量画 PNG。\n"
                "运行前会先做列名预检，告诉你哪一列对不上。",
                ("subprocess", "plot_curves.py"),
            ),
        ],
    ),
    (
        "📝 报告排版",
        [
            (
                "正文排版引擎",
                "body_format",
                "扫描 Word 当前活动文档，按 04_Config/report_style_config.json 自动套用字体、间距、缩进、大纲级别。\n"
                "运行前会自动备份当前文档。",
                ("subprocess", "body_format.py"),
            ),
            (
                "表格排版引擎",
                "table_format",
                "对 Word 文档里所有表格统一字号、行高、表名样式，并把空单元格高亮。",
                ("subprocess", "table_format.py"),
            ),
            (
                "括号半全角纠偏",
                "bracket_format",
                "通过 Word 通配符引擎全局规范括号：技术参数转半角、国标代号锁全角、第N回半角。",
                ("subprocess", "bracket_format.py"),
            ),
            (
                "交叉引用修复",
                "fix_cross_ref",
                "为所有 REF 域追加 \\* MERGEFORMAT 开关，避免后续编辑丢字号字体。",
                ("subprocess", "fix_cross_ref.py"),
            ),
        ],
    ),
    (
        "📷 照片附录",
        [
            (
                "照片流水线（排序+重编号）",
                "pipeline_sort_renumber",
                "一键完成：按 Excel 缺陷清单顺序重排 Word 表格里的图片+题注 → 题注重编号 → 同步改 Excel 引用。",
                ("subprocess", "pipeline_sort_renumber.py"),
            ),
        ],
    ),
    (
        "📄 转换 / 工具",
        [
            (
                "Word ↔ PDF 转换",
                "word2pdf",
                "Word → PDF 与 PDF → Word 双向转换。",
                ("subprocess", "word2pdf.py"),
            ),
            (
                "PNG 坐标拾取器",
                "coord_picker",
                "在 PNG 底图上拖拽框选，输出 100% 像素坐标 JSON，给手写模拟工具用。",
                ("subprocess", "coord_picker.py"),
            ),
            (
                "手写模拟生成器",
                "auto_filler",
                "读 Excel 数据 + PNG 底图 + JSON 坐标 → 仿生手写体填表，导出 PDF。",
                ("subprocess", "auto_filler.py"),
            ),
        ],
    ),
    (
        "⚙ 配置编辑",
        [
            (
                "报告样式配置（字体/间距）",
                "config_editor",
                "可视化编辑 04_Config/report_style_config.json。\n"
                "本工具直接在主窗口右侧打开，修改完保存即生效，无需切换。",
                ("embed", "config_editor:ConfigEditorPanel"),
            ),
            (
                "曲线模板（绘图）",
                "curve_template_editor",
                "可视化编辑 04_Config/curve_templates.json。\n"
                "强烈建议先点'挂载参考 Excel'，让所有列名变成下拉选择，避免手输错。",
                ("embed", "curve_template_editor:CurveTemplateEditorPanel"),
            ),
        ],
    ),
]


# ============================================================
# 主控制台
# ============================================================
class MainDashboard:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("工程自动化主控制台 V3")
        self.root.geometry("1280x820")
        self.root.minsize(1024, 640)

        # 当前选中的工具
        self.current_tool: ToolEntry | None = None

        # subprocess 状态
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue = queue.Queue()

        # 内嵌面板：缓存已经构造好的 Panel 实例（避免每次切换重建）
        self._embedded_panels: dict[str, ctk.CTkFrame] = {}
        self._current_embedded: ctk.CTkFrame | None = None

        self._build_layout()
        # 默认选第一个工具
        self._select_tool(WORKFLOW_GROUPS[0][1][0])
        self._poll_log_queue()

    # ============================================================
    # 布局
    # ============================================================
    def _build_layout(self) -> None:
        # 顶栏
        header = ctk.CTkFrame(
            self.root, height=60, corner_radius=0, fg_color=("#0078d4", "#1f3a5f")
        )
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="工程自动化主控制台", font=("微软雅黑", 18, "bold"), text_color="white"
        ).pack(side="left", padx=24, pady=14)
        ctk.CTkLabel(
            header,
            text="V3 · 嵌入式面板 + 实时日志",
            font=("Consolas", 11),
            text_color=("#cce4ff", "#aac5e0"),
        ).pack(side="left", pady=18)

        # 主体：左右分栏
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # ===== 左侧：分组侧边栏 =====
        sidebar = ctk.CTkFrame(body, width=270, corner_radius=0, fg_color=("gray92", "gray18"))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="按工作流选择工具",
            font=("微软雅黑", 12, "bold"),
            text_color="gray55",
            anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 6))

        self.sidebar_scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.sidebar_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._tool_buttons: dict[str, ctk.CTkButton] = {}
        self._build_sidebar()

        # ===== 右侧：内容区 =====
        self.right_pane = ctk.CTkFrame(body, fg_color="transparent")
        self.right_pane.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        # 工具说明卡片（永远显示）
        self.info_card = ctk.CTkFrame(self.right_pane, corner_radius=12)
        self.info_card.pack(fill="x")

        info_inner = ctk.CTkFrame(self.info_card, fg_color="transparent")
        info_inner.pack(fill="x", padx=22, pady=14)

        title_row = ctk.CTkFrame(info_inner, fg_color="transparent")
        title_row.pack(fill="x")
        self.info_title = ctk.CTkLabel(
            title_row, text="—", font=("微软雅黑", 17, "bold"), anchor="w"
        )
        self.info_title.pack(side="left")
        self.info_kind_badge = ctk.CTkLabel(
            title_row,
            text="",
            font=("微软雅黑", 10, "bold"),
            corner_radius=6,
            fg_color="transparent",
            text_color="white",
            width=80,
            height=22,
        )
        self.info_kind_badge.pack(side="left", padx=10)

        self.info_desc = ctk.CTkLabel(
            info_inner,
            text="",
            font=("微软雅黑", 12),
            text_color=("gray25", "gray85"),
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.info_desc.pack(fill="x", anchor="w", pady=(8, 0))

        # 操作按钮（启动/停止/清空 - 仅 subprocess 模式有效）
        self.action_row = ctk.CTkFrame(info_inner, fg_color="transparent")
        self.action_row.pack(fill="x", pady=(12, 0))

        self.btn_run = ctk.CTkButton(
            self.action_row,
            text="▶ 启动该工具",
            height=36,
            width=150,
            font=("微软雅黑", 12, "bold"),
            command=self._launch_current,
        )
        self.btn_run.pack(side="left", padx=(0, 8))
        attach_help(self.btn_run, "启动该工具的子进程；执行过程中的输出会实时显示在下方日志面板。")

        self.btn_stop = ctk.CTkButton(
            self.action_row,
            text="■ 停止运行",
            height=36,
            width=110,
            font=("微软雅黑", 12),
            fg_color="#aa3333",
            hover_color="#cc4444",
            command=self._stop_current,
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=4)
        attach_help(
            self.btn_stop,
            "向子进程发 terminate 信号。\n如果工具正在改 Word 文档，可能会保留半成品。",
        )

        self.btn_clear = ctk.CTkButton(
            self.action_row,
            text="🧹 清空日志",
            height=36,
            width=100,
            font=("微软雅黑", 12),
            fg_color="gray45",
            hover_color="gray55",
            command=self._clear_log,
        )
        self.btn_clear.pack(side="left", padx=4)

        self.run_status = ctk.CTkLabel(
            self.action_row,
            text="● 空闲",
            font=("微软雅黑", 12, "bold"),
            text_color="gray60",
        )
        self.run_status.pack(side="right", padx=8)

        # 中部：工具内容区（嵌入模式下放 Panel；subprocess 模式下放日志）
        self.content_holder = ctk.CTkFrame(self.right_pane, corner_radius=12)
        self.content_holder.pack(fill="both", expand=True, pady=(14, 0))

        # 日志面板（subprocess 模式默认显示在 content_holder 里）
        self._build_log_panel_in(self.content_holder)

    def _build_log_panel_in(self, parent: ctk.CTkFrame) -> None:
        log_header = ctk.CTkFrame(parent, fg_color="transparent", height=34)
        log_header.pack(fill="x", padx=18, pady=(10, 0))
        log_header.pack_propagate(False)
        ctk.CTkLabel(
            log_header, text="📡 实时日志", font=("微软雅黑", 13, "bold"), anchor="w"
        ).pack(side="left")

        self.log_text = ctk.CTkTextbox(
            parent,
            font=("Consolas", 11),
            wrap="word",
            fg_color=("gray97", "gray12"),
            text_color=("gray10", "gray88"),
        )
        self.log_text.pack(fill="both", expand=True, padx=14, pady=10)
        self.log_text.insert("end", "就绪。在左侧选择一个工具开始。\n")
        self.log_text.configure(state="disabled")

    def _build_sidebar(self) -> None:
        for group_name, tools in WORKFLOW_GROUPS:
            cat = ctk.CTkLabel(
                self.sidebar_scroll,
                text=group_name,
                font=("微软雅黑", 12, "bold"),
                anchor="w",
                text_color=("gray35", "gray70"),
            )
            cat.pack(fill="x", padx=8, pady=(12, 4))

            for entry in tools:
                display_name, key, _desc, (kind, _) = entry
                # 嵌入式工具加个小标记
                label = display_name if kind == "subprocess" else f"⚙ {display_name}"
                btn = ctk.CTkButton(
                    self.sidebar_scroll,
                    text=label,
                    anchor="w",
                    font=("微软雅黑", 12),
                    height=34,
                    corner_radius=6,
                    fg_color="transparent",
                    text_color=("gray10", "gray90"),
                    hover_color=("gray85", "gray28"),
                    command=lambda e=entry: self._select_tool(e),
                )
                btn.pack(fill="x", padx=4, pady=2)
                self._tool_buttons[key] = btn

    # ============================================================
    # 选中 / 切换工具
    # ============================================================
    def _select_tool(self, entry: ToolEntry) -> None:
        # 如果当前正跑着 subprocess，不让切到另一个工具的运行视图
        if self.proc is not None and self.proc.poll() is None:
            self._append_log(
                f"\n⚠️ 当前有工具在运行（{self.current_tool[0] if self.current_tool else '?'}），仅切换说明。\n"
            )

        self.current_tool = entry
        display_name, key, desc, (kind, target) = entry

        # 高亮当前
        for k, btn in self._tool_buttons.items():
            if k == key:
                btn.configure(fg_color=("#cce4ff", "#1f3a5f"), text_color=("#003a73", "#cce4ff"))
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))

        # 更新说明卡
        self.info_title.configure(text=display_name)
        self.info_desc.configure(text=desc)

        # 根据 kind 切换内容区 + 操作按钮的显隐
        if kind == "embed":
            self.info_kind_badge.configure(text=" 内嵌 ", fg_color="#1aaa55")
            self._show_embed_panel(key, target)
            # 嵌入工具不需要"启动/停止"
            self.btn_run.pack_forget()
            self.btn_stop.pack_forget()
            self.btn_clear.pack_forget()
            self.run_status.configure(text="● 内嵌模式 - 直接编辑", text_color="#1aaa55")
        else:  # subprocess
            self.info_kind_badge.configure(text=" 启动 ", fg_color="#0078d4")
            self._show_log_panel()
            # 恢复按钮（顺序）
            self.btn_run.pack(side="left", padx=(0, 8))
            self.btn_stop.pack(side="left", padx=4)
            self.btn_clear.pack(side="left", padx=4)
            running = self.proc is not None and self.proc.poll() is None
            self.btn_run.configure(state="disabled" if running else "normal")
            self.btn_stop.configure(state="normal" if running else "disabled")
            if not running:
                self.run_status.configure(text="● 空闲", text_color="gray60")

    def _hide_current_content(self) -> None:
        """隐藏 content_holder 里的所有子控件（不销毁）。"""
        for w in self.content_holder.winfo_children():
            w.pack_forget()

    def _show_log_panel(self) -> None:
        self._hide_current_content()
        # 重新 pack 日志相关 widget
        # 我们存了 log_text 引用；header 是临时构造的，简单做法：直接重建一个
        for w in list(self.content_holder.winfo_children()):
            w.destroy()
        self._build_log_panel_in(self.content_holder)

    def _show_embed_panel(self, key: str, target: str) -> None:
        self._hide_current_content()
        # 销毁日志相关，因为 embed 模式不需要
        for w in list(self.content_holder.winfo_children()):
            w.destroy()

        # 缓存 Panel 实例
        if key not in self._embedded_panels:
            module_name, class_name = target.split(":")
            try:
                mod = __import__(module_name)
                cls = getattr(mod, class_name)
                panel = cls(self.content_holder)
            except Exception as e:
                err = ctk.CTkLabel(
                    self.content_holder,
                    text=f"⚠ 无法加载内嵌面板 {target}:\n{e}",
                    font=("微软雅黑", 12),
                    text_color="#aa3333",
                )
                err.pack(pady=20)
                return
            self._embedded_panels[key] = panel

        panel = self._embedded_panels[key]
        panel.pack(fill="both", expand=True)
        self._current_embedded = panel

    # ============================================================
    # subprocess 启动 / 停止 / 日志
    # ============================================================
    def _launch_current(self) -> None:
        if self.current_tool is None:
            return
        kind, target = self.current_tool[3]
        if kind != "subprocess":
            return
        if self.proc is not None and self.proc.poll() is None:
            self._append_log("⚠️ 已有工具在运行，请先停止或等待结束。\n")
            return

        script_path = os.path.join(_THIS_DIR, target)
        if not os.path.exists(script_path):
            self._append_log(f"❌ 缺失模块：{script_path}\n")
            return

        self._clear_log()
        self._append_log(f"🚀 启动 {target} ...\n\n")

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-u", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=_THIS_DIR,
                env=env,
                creationflags=creationflags,
            )
        except Exception as e:
            self._append_log(f"❌ 启动失败：{e}\n")
            self.proc = None
            return

        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.run_status.configure(text="● 运行中", text_color="#1aaa55")

        threading.Thread(target=self._reader_worker, args=(self.proc,), daemon=True).start()

    def _reader_worker(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                line = (
                    chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                )
                self.log_queue.put(line)
        finally:
            proc.stdout.close()
            rc = proc.wait()
            self.log_queue.put(f"\n[进程结束 returncode={rc}]\n")
            self.log_queue.put(("__DONE__", rc))

    def _stop_current(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self._append_log("\n⛔ 用户请求停止...\n")
        try:
            self.proc.terminate()
        except Exception as e:
            self._append_log(f"   terminate 失败: {e}\n")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self._on_proc_done(item[1])
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log_queue)

    def _on_proc_done(self, returncode: int) -> None:
        self.proc = None
        # 仅当当前显示的是 subprocess 工具时复位按钮
        if self.current_tool and self.current_tool[3][0] == "subprocess":
            self.btn_run.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            if returncode == 0:
                self.run_status.configure(text="● 已完成", text_color="#1aaa55")
            else:
                self.run_status.configure(
                    text=f"● 异常退出 (rc={returncode})", text_color="#aa3333"
                )

    def _append_log(self, text: str) -> None:
        # log_text 在嵌入模式下已被销毁；只在它存在时写
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", text)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            pass

    def _clear_log(self) -> None:
        try:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
        except Exception:
            pass


def _main() -> None:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    MainDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    _main()
