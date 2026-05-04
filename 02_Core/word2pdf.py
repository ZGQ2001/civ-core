"""
===============================================================================
脚本名称：文件处理工具箱 (word2pdf_pro.py)
作者: ZGQ
功能概述：
    1. Word 批量转 PDF | 2. PDF 排序合并 | 3. 文档转高清 PNG
V2.3 ：修复日志区权限、按钮对比度及 1080P/125% 缩放适配问题。
===============================================================================
"""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import fitz
import pythoncom
import win32com.client
from pypdf import PdfWriter

# ---------------- 自定义模块集成 ----------------
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ui_components import ModernInfoDialog, ModernProgressConsole


class EngineeringDocTool(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("文件处理工具箱")

        # 界面比例
        self.geometry("550x650")
        self.minsize(500, 650)

        # 数据初始化
        self.word_files = []
        self.word_out_dir = ""
        self.merge_files = []
        self.merge_out_path = ""
        self.png_files = []
        self.png_out_dir = ""

        self.setup_ui()

    def setup_ui(self):
        # 1. 顶部标题区
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(15, 5), fill="x")
        ctk.CTkLabel(
            header_frame, text="🛠️ 工程报告多功能处理平台", font=("微软雅黑", 20, "bold")
        ).pack()

        # 2. 功能选项卡（占据核心高度）
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.pack(padx=20, pady=5, fill="both", expand=True)

        self.tab1 = self.tabview.add(" Word 转 PDF ")
        self.tab2 = self.tabview.add(" PDF 排序合并 ")
        self.tab3 = self.tabview.add(" 文档转高清 PNG ")

        self._build_word_tab()
        self._build_merge_tab()
        self._build_png_tab()

        # 3. 底部日志区（借鉴成熟方案：深色、只读、带标题栏）
        log_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#2b2b2b")
        log_frame.pack(pady=(5, 20), padx=20, fill="x")

        # 日志区状态设为 disabled，禁止用户输入
        self.log_area = ctk.CTkTextbox(
            log_frame,
            height=100,
            font=("Consolas", 12),
            fg_color="#1e1e1e",
            text_color="#a9b7c6",
            corner_radius=8,
            state="disabled",  # 【修复】禁止手动输入
        )
        self.log_area.pack(pady=10, padx=10, fill="both")

    def log(self, msg):
        """线程安全的只读日志刷新逻辑"""
        self.log_area.configure(state="normal")  # 临时开启写入
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state="disabled")  # 再次死锁
        self.update()

    # ==================== UI 布局模板 ====================
    def _create_standard_layout(self, parent, list_title):
        # 主文件列表容器
        frame_main = ctk.CTkFrame(parent, fg_color="transparent")
        frame_main.pack(pady=5, padx=15, fill="both", expand=True)

        ctk.CTkLabel(frame_main, text=list_title, font=("微软雅黑", 13, "bold")).pack(
            pady=(0, 5), anchor="w"
        )

        # 列表框：白色底，深色字
        lbox = tk.Listbox(
            frame_main,
            height=6,
            bg="#ffffff",
            fg="#333333",
            selectbackground="#0078d4",
            selectforeground="#ffffff",
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            font=("微软雅黑", 10),
        )
        lbox.pack(fill="both", expand=True, pady=5)

        btn_box = ctk.CTkFrame(frame_main, fg_color="transparent")
        btn_box.pack(fill="x", pady=(0, 5))

        # 输出路径配置区
        frame_out = ctk.CTkFrame(parent, corner_radius=8, fg_color="#f2f2f2")
        frame_out.pack(pady=10, padx=15, fill="x")

        ent_path = ctk.CTkEntry(
            frame_out, placeholder_text="尚未选择保存路径...", height=32, border_width=1
        )
        ent_path.pack(side="left", padx=10, pady=12, fill="x", expand=True)

        return lbox, btn_box, ent_path, frame_out

    # ==================== 功能页面构建 ====================
    def _build_word_tab(self):
        lbox, b_box, ent, f_out = self._create_standard_layout(self.tab1, "Word 待处理文件列表")
        self.lb_word, self.ent_word = lbox, ent

        ctk.CTkButton(
            b_box, text="添加 Word 文件", width=120, height=30, command=self.add_word_files
        ).pack(side="left", padx=5)
        # 【修复】按钮颜色调优：灰色边框 + 深灰色字体，确保清晰
        ctk.CTkButton(
            b_box,
            text="清空",
            width=80,
            height=30,
            fg_color="#e0e0e0",
            text_color="#2b2b2b",
            hover_color="#d0d0d0",
            border_width=0,
            command=self.clear_word,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            f_out, text="选择输出目录", width=120, height=30, command=self.set_word_out
        ).pack(side="right", padx=10)

        self.btn_run_word = ctk.CTkButton(
            self.tab1,
            text="🚀 启动批量转换 PDF",
            font=("微软雅黑", 16, "bold"),
            height=45,
            corner_radius=10,
            command=self.run_word_task,
        )
        self.btn_run_word.pack(pady=(10, 15))

    def _build_merge_tab(self):
        lbox, b_box, ent, f_out = self._create_standard_layout(
            self.tab2, "PDF 合并列表 (自上而下合并)"
        )
        self.lb_merge, self.ent_merge = lbox, ent

        ctk.CTkButton(
            b_box, text="添加 PDF", width=100, height=30, command=self.add_merge_files
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            b_box, text="向上移", width=70, height=30, command=lambda: self.move_item(-1)
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            b_box, text="向下移", width=70, height=30, command=lambda: self.move_item(1)
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            b_box,
            text="清空",
            width=80,
            height=30,
            fg_color="#e0e0e0",
            text_color="#2b2b2b",
            command=self.clear_merge,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            f_out, text="指定文件名", width=120, height=30, command=self.set_merge_out
        ).pack(side="right", padx=10)

        self.btn_run_merge = ctk.CTkButton(
            self.tab2,
            text="🔗 开始合并序列",
            font=("微软雅黑", 16, "bold"),
            height=45,
            corner_radius=10,
            command=self.run_merge_task,
        )
        self.btn_run_merge.pack(pady=(10, 15))

    def _build_png_tab(self):
        lbox, b_box, ent, f_out = self._create_standard_layout(self.tab3, "待转高清底图文件列表")
        self.lb_png, self.ent_png = lbox, ent

        ctk.CTkButton(
            b_box, text="添加文件", width=120, height=30, command=self.add_png_files
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            b_box,
            text="清空",
            width=80,
            height=30,
            fg_color="#e0e0e0",
            text_color="#2b2b2b",
            command=self.clear_png,
        ).pack(side="left", padx=5)

        cfg_row = ctk.CTkFrame(f_out, fg_color="transparent")
        cfg_row.pack(side="left", padx=10)
        ctk.CTkLabel(cfg_row, text="DPI:", font=("微软雅黑", 12)).pack(side="left", padx=5)
        self.cb_dpi = ctk.CTkComboBox(cfg_row, values=["150", "300", "600"], width=90, height=30)
        self.cb_dpi.set("300")
        self.cb_dpi.pack(side="left")

        ctk.CTkButton(
            f_out, text="设置保存位置", width=120, height=30, command=self.set_png_out
        ).pack(side="right", padx=10)

        self.btn_run_png = ctk.CTkButton(
            self.tab3,
            text="🖼️ 批量渲染底图",
            font=("微软雅黑", 16, "bold"),
            height=45,
            corner_radius=10,
            command=self.run_png_task,
        )
        self.btn_run_png.pack(pady=(10, 15))

    # ==================== 逻辑处理 ====================
    def add_word_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Word", "*.doc;*.docx")])
        for f in files:
            p = os.path.abspath(f)
            if p not in self.word_files:
                self.word_files.append(p)
                self.lb_word.insert(tk.END, f"  📄 {os.path.basename(p)}")

    def clear_word(self):
        self.word_files.clear()
        self.lb_word.delete(0, tk.END)

    def set_word_out(self):
        d = filedialog.askdirectory()
        if d:
            self.word_out_dir = d
            self.ent_word.configure(state="normal")
            self.ent_word.delete(0, tk.END)
            self.ent_word.insert(0, d)

    def add_merge_files(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for f in files:
            p = os.path.abspath(f)
            if p not in self.merge_files:
                self.merge_files.append(p)
                self.lb_merge.insert(tk.END, f"  📑 {os.path.basename(p)}")

    def move_item(self, step):
        idx = self.lb_merge.curselection()
        if not idx:
            return
        i = idx[0]
        ni = i + step
        if 0 <= ni < len(self.merge_files):
            self.merge_files[i], self.merge_files[ni] = self.merge_files[ni], self.merge_files[i]
            txt = self.lb_merge.get(i)
            self.lb_merge.delete(i)
            self.lb_merge.insert(ni, txt)
            self.lb_merge.select_set(ni)

    def clear_merge(self):
        self.merge_files.clear()
        self.lb_merge.delete(0, tk.END)

    def set_merge_out(self):
        f = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="合并结果.pdf")
        if f:
            self.merge_out_path = f
            self.ent_merge.configure(state="normal")
            self.ent_merge.delete(0, tk.END)
            self.ent_merge.insert(0, f)

    def add_png_files(self):
        files = filedialog.askopenfilenames(filetypes=[("支持格式", "*.doc;*.docx;*.pdf")])
        for f in files:
            p = os.path.abspath(f)
            if p not in self.png_files:
                self.png_files.append(p)
                self.lb_png.insert(tk.END, f"  🖼️ {os.path.basename(p)}")

    def clear_png(self):
        self.png_files.clear()
        self.lb_png.delete(0, tk.END)

    def set_png_out(self):
        d = filedialog.askdirectory()
        if d:
            self.png_out_dir = d
            self.ent_png.configure(state="normal")
            self.ent_png.delete(0, tk.END)
            self.ent_png.insert(0, d)

    # ==================== 核心引擎 ====================
    def _mount_word_engine(self):
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            return word, "Microsoft Word"
        except:
            try:
                word = win32com.client.DispatchEx("KWPS.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                return word, "WPS Office"
            except:
                raise Exception("未检测到 Word/WPS 环境")

    def run_word_task(self):
        if not self.word_files or not self.word_out_dir:
            ModernInfoDialog("提示", "请先添加文件并设置输出路径！").show()
            return
        self.btn_run_word.configure(state="disabled")
        threading.Thread(target=self._proc_word, daemon=True).start()

    def _proc_word(self):
        pythoncom.CoInitialize()
        word_app = None
        total = len(self.word_files)
        progress = ModernProgressConsole("批量转换 PDF", total)
        try:
            word_app, name = self._mount_word_engine()
            self.log(f"已启动引擎: {name}")
            for i, p in enumerate(self.word_files):
                if progress.is_cancelled:
                    break
                self.log(f"正在转换: {os.path.basename(p)}")
                progress.update_progress(i + 1, f"进度: {i + 1}/{total}")
                out = os.path.join(
                    self.word_out_dir, os.path.splitext(os.path.basename(p))[0] + ".pdf"
                )
                doc = word_app.Documents.Open(p, ReadOnly=1)
                doc.SaveAs(os.path.abspath(out), FileFormat=17)
                doc.Close(0)
            self.log("✅ 转换任务完成")
            ModernInfoDialog("任务成功", f"成功将 {total} 个文件转换为 PDF。").show()
        except Exception as e:
            self.log(f"❌ 错误: {e!s}")
        finally:
            if word_app:
                word_app.Quit()
            pythoncom.CoUninitialize()
            progress.close()
            self.after(0, lambda: self.btn_run_word.configure(state="normal"))

    def run_merge_task(self):
        if len(self.merge_files) < 2 or not self.merge_out_path:
            ModernInfoDialog("提示", "合并至少需要 2 个文件！").show()
            return
        self.btn_run_merge.configure(state="disabled")
        threading.Thread(target=self._proc_merge, daemon=True).start()

    def _proc_merge(self):
        writer = PdfWriter()
        total = len(self.merge_files)
        progress = ModernProgressConsole("PDF 排序合并", total)
        try:
            self.log("--- 启动合并序列 ---")
            for i, p in enumerate(self.merge_files):
                if progress.is_cancelled:
                    break
                self.log(f"追加: {os.path.basename(p)}")
                progress.update_progress(i + 1, f"正在合并第 {i + 1} 个文件")
                writer.append(p)
            with open(self.merge_out_path, "wb") as f:
                writer.write(f)
            self.log(f"✅ 合并成功: {self.merge_out_path}")
            ModernInfoDialog("任务成功", f"PDF 已合并保存至：\n{self.merge_out_path}").show()
        except Exception as e:
            self.log(f"❌ 失败: {e!s}")
        finally:
            writer.close()
            progress.close()
            self.after(0, lambda: self.btn_run_merge.configure(state="normal"))

    def run_png_task(self):
        if not self.png_files or not self.png_out_dir:
            ModernInfoDialog("提示", "请检查待转列表和输出文件夹！").show()
            return
        self.btn_run_png.configure(state="disabled")
        threading.Thread(target=self._proc_png, daemon=True).start()

    def _proc_png(self):
        pythoncom.CoInitialize()
        word_app = None
        dpi = int(self.cb_dpi.get())
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        total = len(self.png_files)
        progress = ModernProgressConsole("高清底图渲染", total)
        try:
            for i, p in enumerate(self.png_files):
                if progress.is_cancelled:
                    break
                progress.update_progress(i + 1, f"处理中: {os.path.basename(p)}")
                ext = os.path.splitext(p)[1].lower()
                pdf_path = p
                is_tmp = False

                if ext in [".doc", ".docx"]:
                    if not word_app:
                        word_app, _ = self._mount_word_engine()
                    pdf_path = os.path.join(self.png_out_dir, "temp_render.pdf")
                    doc = word_app.Documents.Open(p, ReadOnly=1)
                    doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)
                    doc.Close(0)
                    is_tmp = True

                self.log(f"渲染图像: {os.path.basename(p)}")
                doc_pdf = fitz.open(pdf_path)
                for page_idx in range(len(doc_pdf)):
                    pix = doc_pdf[page_idx].get_pixmap(matrix=mat, alpha=False)
                    out_name = f"{os.path.splitext(os.path.basename(p))[0]}_P{page_idx + 1}.png"
                    pix.save(os.path.join(self.png_out_dir, out_name))
                doc_pdf.close()
                if is_tmp and os.path.exists(pdf_path):
                    os.remove(pdf_path)
            self.log("✅ 渲染完成")
            ModernInfoDialog("任务成功", "PNG 已成功保存。").show()
        except Exception as e:
            self.log(f"❌ 异常: {e!s}")
        finally:
            if word_app:
                word_app.Quit()
            pythoncom.CoUninitialize()
            progress.close()
            self.after(0, lambda: self.btn_run_png.configure(state="normal"))


if __name__ == "__main__":
    # 高 DPI 兼容性处理
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    app = EngineeringDocTool()
    app.mainloop()
