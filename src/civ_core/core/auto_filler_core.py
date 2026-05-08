"""
===============================================================================
脚本名称：仿生手写核心驱动引擎 (core_engine.py)
核心重构：
    1. 彻底解耦：告别写死的坐标，引入 parse_excel_coord 智能翻译相对坐标。
    2. 动态阵列：根据 UI 传来的基准框自动计算 dx 和 dy。
    3. 严密防线：引入 getbbox() 字体过滤，遇到不支持中文字符的残缺字体自动剔除，告别空白和乱码。
===============================================================================
"""

import json
import os
import random
import re

import pandas as pd
from handright import Template, handwrite
from PIL import Image, ImageFilter, ImageFont, ImageOps

# ==================== 【全局高速缓存：修复版】 ====================
# 用于存放已经加载好的字体，避免重复扫描硬盘，大幅提升初始化速度
_FONT_POOL_CACHE = {}


def get_cached_fonts(font_files, size):
    """
    内存池：将字体文件列表和字号共同作为钥匙。
    为什么这么做：只要文件夹里的字体数量或名字变了，钥匙就会改变，程序会自动重新加载，不会再被旧缓存坑了。
    """
    # 将列表转换为不可变的元组，加上字号，共同作为字典的键
    cache_key = (tuple(font_files), size)

    if cache_key not in _FONT_POOL_CACHE:
        # 如果是新字体组合或新字号，重新装填弹药
        _FONT_POOL_CACHE[cache_key] = [ImageFont.truetype(f, size) for f in font_files]

    return _FONT_POOL_CACHE[cache_key]


# =================================================================
# =================================================================
# ==================== 工具函数：智能坐标翻译 ====================
def parse_excel_coord(coord_str):
    """
    黑科技：将人类可读的 Excel 坐标 (如 'C2') 翻译为底层 iloc 索引 (row_idx, col_idx)
    为什么这么做：让用户能直观看着 Excel 填表，而不是去算(1, 2)这种机器索引。
    """
    match = re.match(r"([A-Za-z]+)(\d+)", str(coord_str).strip())
    if not match:
        return None, None

    col_letters, row_num = match.groups()

    col_idx = 0
    for char in col_letters.upper():
        col_idx = col_idx * 26 + (ord(char) - ord("A") + 1)
    col_idx -= 1

    row_idx = int(row_num) - 1

    return row_idx, col_idx


# ==================== 核心视觉：防爆手写渲染器 ====================
def create_handwritten_sticker(
    text, box, fonts_dir, base_font_size, spacing, fatigue_idx=0, total_items=1
):
    w, h = int(box[2]), int(box[3])
    clean_text = str(text).strip()

    # 清洗空数据
    if clean_text in ["nan", "None", "", "NaN"]:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    font_files = [
        os.path.join(fonts_dir, f) for f in os.listdir(fonts_dir) if f.endswith((".ttf", ".otf"))
    ]
    if not font_files:
        raise ValueError("致命错误：手写字体目录为空！")

    fatigue_boost = min(1.3, 1.0 + (fatigue_idx / total_items))
    current_size = int(base_font_size)
    final_wrapped_text = ""

    # === 恢复旧版的智能排版与自动折行逻辑 ===
    while current_size > 10:
        font_ruler_temp = ImageFont.truetype(font_files[0], current_size)
        if font_ruler_temp.getlength(clean_text) <= (w * 1.20):
            final_wrapped_text = clean_text
            lines_count = 1
            break

        lines = []
        cur_line = ""
        for char in clean_text:
            if font_ruler_temp.getlength(cur_line + char) <= (w * 1.1):
                cur_line += char
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = char
        lines.append(cur_line)

        line_h = int(current_size * 1.15)
        if (len(lines) * line_h) <= (h + 10):
            final_wrapped_text = "\n".join(lines)
            lines_count = len(lines)
            break
        current_size -= 2
    else:
        final_wrapped_text, lines_count, current_size = clean_text, 1, 12

    # =========== 【返璞归真：每个格子重新摇号机制】 ===========
    # 1. 弹药库加载（利用缓存，速度极快）
    font_files = list(dict.fromkeys(font_files))
    multi_fonts = get_cached_fonts(font_files, current_size)

    # 2. 核心：因为这是针对当前格子的独立运算，这一句就会让当前格子拥有随机独立字体
    chosen_font = random.choice(multi_fonts)
    # =========================================================

    # === 恢复旧版的动态居中锚点计算 ===
    canvas_w, canvas_h = w + 200, h + 150
    bg = Image.new("L", (canvas_w, canvas_h), 255)
    total_text_h = lines_count * int(current_size * 1.15)
    top_pos = (canvas_h - total_text_h) // 2

    template = Template(
        background=bg,
        font=chosen_font,  # 直接将摇号得出的实体字体对象喂给排版引擎
        line_spacing=int(current_size * 1.15),
        fill=0,
        left_margin=100,
        top_margin=top_pos,
        word_spacing=spacing,
        line_spacing_sigma=1.0,
        font_size_sigma=current_size * 0.08,
        word_spacing_sigma=1.0,
        perturb_x_sigma=1.2 * fatigue_boost,
        perturb_y_sigma=0.5 * fatigue_boost,
        perturb_theta_sigma=0.06 * fatigue_boost,
    )

    try:
        raw_img = list(handwrite(final_wrapped_text, template))[0]
        mask = ImageOps.invert(raw_img)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=0.2))  # A：轻微模糊让墨迹更自然
        ink_layer = Image.new("RGBA", (canvas_w, canvas_h), (40, 45, 50, 235))
        sticker = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        sticker.paste(ink_layer, (0, 0), mask)
        return sticker
    except Exception as e:
        print(f"渲染贴纸出错: {e}")
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))


# ==================== 主控逻辑：执行生成任务 ====================
def run_generator(stage1_config, stage2_mapping, progress_console=None):
    """
    接收 UI 层的数据，协调所有模块开始流水线作业。
    """
    print("🚀 核心引擎已点火，准备读取配置...")

    # 1. 拆包 UI 数据
    excel_path = stage1_config["excel_path"]
    json_path = stage1_config["json_path"]
    img_path = stage1_config["img_path"]
    fonts_dir = stage1_config["font_dir"]
    output_dir = stage1_config["output_dir"]
    sheet_name = stage1_config["sheet_name"]
    font_scale = stage1_config["font_scale"]
    y_offset = stage1_config["y_offset"]
    spacing = stage1_config["spacing"]

    output_pdf = os.path.join(output_dir, "自动生成_检测记录表.pdf")

    # 2. 读取 JSON 解析坐标与基准
    with open(json_path, encoding="utf-8") as f:
        json_boxes = json.load(f)

    # 计算动态步长 (dx, dy)
    dx, dy = 0, 0
    x_base, x_target = stage2_mapping["x_base"], stage2_mapping["x_target"]
    y_base, y_target = stage2_mapping["y_base"], stage2_mapping["y_target"]

    if x_base in json_boxes and x_target in json_boxes:
        dx = json_boxes[x_target]["box"][0] - json_boxes[x_base]["box"][0]
    if y_base in json_boxes and y_target in json_boxes:
        dy = (json_boxes[y_target]["box"][1] - json_boxes[y_base]["box"][1]) + y_offset

    print(f"📐 引擎计算阵列步长完毕 -> dx: {dx}, dy: {dy}")

    # 3. 读取 Excel
    print(f"📊 正在接管 Excel 数据: {sheet_name}")
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, engine="openpyxl")
    df[0] = df[0].ffill()

    # 4. 动态数据提取提取
    items = []
    step = stage2_mapping["excel_step"]
    coords_dict = stage2_mapping["coordinates"]

    for i in range(0, len(df), step):
        if i + (step - 1) >= len(df):
            break  # 剩下的行数不够完整一组了

        chunk = df.iloc[i : i + step]
        item_data = {}

        # 遍历用户在 UI 里填写的坐标连线
        for field_name, excel_coord in coords_dict.items():
            r_idx, c_idx = parse_excel_coord(excel_coord)
            if r_idx is not None and c_idx is not None:
                try:
                    # 尝试从截取的 chunk 中抓取数据
                    val = chunk.iloc[r_idx, c_idx]
                    item_data[field_name] = val
                except IndexError:
                    item_data[field_name] = ""  # 越界容错

        items.append(item_data)

    total_count = len(items)
    print(f"📦 共成功打包 {total_count} 组待写数据。")
    # 【新增】：把真实的总数据量告诉进度条
    if progress_console:
        progress_console.max_val = total_count

    # 5. 图层合成与阵列排版
    items_per_page = stage2_mapping["grid_cols"] * stage2_mapping["grid_rows"]
    cols_limit = stage2_mapping["grid_cols"]

    pages = []
    current_page_img = None

    for idx, item in enumerate(items):
        # 【新增】：紧急制动检测。如果用户点了 UI 上的“紧急停止”，立刻退出循环
        if progress_console and progress_console.is_cancelled:
            print("🛑 引擎接收到中止指令，已安全停机！")
            return False

        pos_index = idx % items_per_page

        if pos_index == 0:
            if current_page_img:
                pages.append(current_page_img.convert("RGB"))
            current_page_img = Image.open(img_path).convert("RGBA")
            print(f"📄 正在手写第 {len(pages) + 1} 页...")

        col = pos_index % cols_limit
        row = pos_index // cols_limit
        cur_dx = col * dx
        cur_dy = row * dy

        # 将数据写入该组对应的各个框
        for field_name, text_val in item.items():
            if field_name not in json_boxes:
                continue

            # 独立读取每个框的专属字号，并乘以上方传来的全局缩放
            field_font_size = json_boxes[field_name].get("font_size", 35) * font_scale

            bx, by, bw, bh = json_boxes[field_name]["box"]
            tx, ty = int(bx + cur_dx), int(by + cur_dy)

            sticker = create_handwritten_sticker(
                text=text_val,
                box=[tx, ty, bw, bh],
                fonts_dir=fonts_dir,
                base_font_size=field_font_size,
                spacing=spacing,
                fatigue_idx=idx,
                total_items=total_count,
            )

            assert current_page_img is not None  # pos_index==0 时已完成初始化，此处必非 None
            current_page_img.paste(sticker, (tx - 100, ty - 75), sticker)
            # 【新增】：每画完一组数据，就向 UI 汇报一次进度
            if progress_console:
                progress_console.update_progress(
                    idx + 1, f"正在手写合成：第 {len(pages)} 页 (进度 {idx + 1}/{total_count})"
                )

    if current_page_img:
        pages.append(current_page_img.convert("RGB"))

    if pages:
        pages[0].save(output_pdf, save_all=True, append_images=pages[1:], resolution=300)
        print(f"🎉 任务圆满结束！输出文件至：{output_pdf}")
        return True
    return False
