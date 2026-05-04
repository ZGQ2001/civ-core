"""
===============================================================================
脚本名称：PNG 原图区域框选拾取工具 (01_png_box_picker.py)
功能概述：
    加载纯正的 PNG 底图，使用鼠标拖拽框选填数格子。
    自动换算屏幕缩放率，导出 100% 绝对像素坐标到 JSON，杜绝 DPI 换算误差！
===============================================================================
"""

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk


class PNGBoXPicker:
    def __init__(self, png_path):
        self.png_path = png_path

        # 1. 加载纯正的 PNG 原图，获取绝对像素尺寸
        self.img_full = Image.open(png_path)
        self.orig_w, self.orig_h = self.img_full.size

        # 缩放、平移与交互变量
        self.zoom_scale = 1.0
        self.offset_x, self.offset_y = 0, 0
        self.last_mouse_x, self.last_mouse_y = 0, 0

        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.saved_coords = {}
        self.has_unsaved_changes = False

        # GUI 构建
        self.root = tk.Tk()
        self.root.title(f"PNG 原图坐标拾取器 - 真实像素: {self.orig_w}x{self.orig_h}")
        self.root.geometry("1100x900")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.canvas = tk.Canvas(self.root, bg="#2b2b2b", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-3>", self.start_pan)
        self.canvas.bind("<B3-Motion>", self.do_pan)
        self.root.bind("<Control-s>", lambda e: self.save_to_json())
        self.root.bind("<Configure>", self.on_window_resize)
        self.root.bind("<Escape>", lambda e: self.on_closing())

        self.status = tk.Label(
            self.root,
            text="左键拖拽框选 | 右键平移 | Ctrl+滚轮缩放 | Ctrl+S 导出 JSON",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("微软雅黑", 10),
            bg="#f0f0f0",
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.tk_img = None
        self.first_show = True

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="red",
            width=2,
            dash=(4, 4),
        )

    def on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        if not self.rect_id:
            return

        end_x, end_y = event.x, event.y
        self.canvas.delete(self.rect_id)
        self.rect_id = None

        win_w, win_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        img_w, img_h = self.img_full.size
        dw, dh = img_w * self.zoom_scale, img_h * self.zoom_scale
        img_left = win_w // 2 + self.offset_x - (dw / 2)
        img_top = win_h // 2 + self.offset_y - (dh / 2)

        # 【核心突破】：换算回原图的绝对像素坐标
        real_x1 = ((min(self.start_x, end_x) - img_left) / dw) * self.orig_w
        real_y1 = ((min(self.start_y, end_y) - img_top) / dh) * self.orig_h
        real_x2 = ((max(self.start_x, end_x) - img_left) / dw) * self.orig_w
        real_y2 = ((max(self.start_y, end_y) - img_top) / dh) * self.orig_h

        real_w = real_x2 - real_x1
        real_h = real_y2 - real_y1

        if real_w < 5 or real_h < 5:
            return

        field_name = simpledialog.askstring(
            "命名填写区域", "请输入此区域对应的 Excel 表头名称：", parent=self.root
        )
        if field_name:
            self.saved_coords[field_name] = {
                "box": [int(real_x1), int(real_y1), int(real_w), int(real_h)],  # 绝对像素取整
                "font_size": 35,  # 默认字号 (针对 300DPI 大图)
                "color": [0, 0, 0],  # 黑色
                "line_spacing": 1.5,
            }
            self.has_unsaved_changes = True
            self.render_image()

    def save_to_json(self):
        if not self.saved_coords:
            messagebox.showwarning("提示", "当前没有框选任何区域！")
            return False

        save_path = filedialog.asksaveasfilename(
            title="保存坐标配置文件",
            initialdir=os.path.dirname(self.png_path),
            initialfile="record_mapping.json",
            filetypes=[("JSON files", "*.json")],
        )
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.saved_coords, f, ensure_ascii=False, indent=4)
            self.has_unsaved_changes = False
            messagebox.showinfo("成功", f"配置文件已导出至：\n{save_path}")
            return True
        return False

    def on_closing(self):
        if self.has_unsaved_changes:
            ans = messagebox.askyesnocancel("退出确认", "有未保存的框选数据，是否保存？")
            if ans is True:
                if self.save_to_json():
                    self.root.destroy()
            elif ans is False:
                self.root.destroy()
        else:
            self.root.destroy()

    def render_image(self):
        win_w, win_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if win_w <= 1:
            return
        img_w, img_h = self.img_full.size
        dw, dh = int(img_w * self.zoom_scale), int(img_h * self.zoom_scale)
        resample = Image.Resampling.LANCZOS if self.zoom_scale > 0.5 else Image.Resampling.NEAREST
        self.tk_img = ImageTk.PhotoImage(self.img_full.resize((dw, dh), resample))
        self.canvas.delete("all")
        self.canvas.create_image(
            win_w // 2 + self.offset_x, win_h // 2 + self.offset_y, image=self.tk_img
        )
        self.draw_markers()

    def draw_markers(self):
        win_w, win_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        img_w, img_h = self.img_full.size
        dw, dh = img_w * self.zoom_scale, img_h * self.zoom_scale
        img_left = win_w // 2 + self.offset_x - (dw / 2)
        img_top = win_h // 2 + self.offset_y - (dh / 2)

        for name, data in self.saved_coords.items():
            box = data["box"]
            screen_x = (box[0] / self.orig_w) * dw + img_left
            screen_y = (box[1] / self.orig_h) * dh + img_top
            screen_w = (box[2] / self.orig_w) * dw
            screen_h = (box[3] / self.orig_h) * dh

            self.canvas.create_rectangle(
                screen_x,
                screen_y,
                screen_x + screen_w,
                screen_y + screen_h,
                outline="#00a8ff",
                width=2,
            )
            self.canvas.create_text(
                screen_x,
                screen_y - 12,
                text=name,
                anchor=tk.W,
                fill="#00a8ff",
                font=("微软雅黑", 11, "bold"),
            )

    def on_window_resize(self, event):
        if self.first_show:
            win_w, win_h = event.width, event.height
            img_w, img_h = self.img_full.size
            self.zoom_scale = min(win_w / img_w, win_h / img_h) * 0.95
            self.first_show = False
        self.render_image()

    def on_mousewheel(self, event):
        if event.state & 0x0004:
            zoom_step = 1.1 if event.delta > 0 else 0.9
            win_w, win_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            mouse_rel_x = event.x - (win_w // 2 + self.offset_x)
            mouse_rel_y = event.y - (win_h // 2 + self.offset_y)
            old_scale = self.zoom_scale
            self.zoom_scale = max(0.1, min(self.zoom_scale * zoom_step, 5.0))
            real_step = self.zoom_scale / old_scale
            self.offset_x -= mouse_rel_x * real_step - mouse_rel_x
            self.offset_y -= mouse_rel_y * real_step - mouse_rel_y
            self.render_image()

    def start_pan(self, event):
        self.last_mouse_x, self.last_mouse_y = event.x, event.y

    def do_pan(self, event):
        self.offset_x += event.x - self.last_mouse_x
        self.offset_y += event.y - self.last_mouse_y
        self.last_mouse_x, self.last_mouse_y = event.x, event.y
        self.render_image()


if __name__ == "__main__":
    temp_root = tk.Tk()
    temp_root.withdraw()
    png_file = filedialog.askopenfilename(
        title="选择检测记录表 PNG 底图", filetypes=[("PNG/JPG 图片", "*.png *.jpg *.jpeg")]
    )
    temp_root.destroy()
    if png_file:
        app = PNGBoXPicker(png_file)
        app.root.mainloop()
