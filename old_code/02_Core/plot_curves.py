"""
批量绘图工具 (plot_curves.py)

从 Excel 某个 Sheet 按行读取数据，套用 04_Config/curve_templates.json 里的模板，
批量画曲线 PNG 存到指定目录。模板可扩展（新项目=新模板条目），坐标轴 / 列名 / 曲线
段数都在 JSON 里描述。

业务逻辑（load_template / build_jobs / run_plot_curves）纯参数；UI 在 _main()。
"""

import json
import os
import re
import sys
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.io_helpers import (
    enable_line_buffered_stdout,
    pick_excel_file,
    read_sheet_names,
)
from common.plot_helpers import render_plot
from common.types import AxisSpec, CurveSeries, PlotJob
from common.ui_helpers import field_dir, field_sheet_select
from ui_components import ModernConfirmDialog, ModernDynamicFormDialog, ModernInfoDialog

DEFAULT_TEMPLATES_PATH = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "04_Config", "curve_templates.json")
)


# ==========================================
# 模块 1：核心业务（纯参数，可被其他工具复用）
# ==========================================
def load_templates(path: str = DEFAULT_TEMPLATES_PATH) -> dict[str, Any]:
    """读取曲线模板库 JSON。失败抛异常。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"曲线模板库不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_template_names(templates: dict[str, Any]) -> list[str]:
    """筛掉以 _ 开头的注释字段。"""
    return [k for k in templates.keys() if not k.startswith("_")]


def _axis_spec_from_dict(d: dict[str, Any]) -> AxisSpec:
    """JSON 的 {label, range} → AxisSpec。range 兼容 list 和 null。"""
    rng = d.get("range")
    if rng is None:
        return AxisSpec(label=d["label"], range=None)
    return AxisSpec(label=d["label"], range=(float(rng[0]), float(rng[1]), float(rng[2])))


def _normalize_col(name: str) -> str:
    """列名标准化：去所有空白（含全角空格 \\u3000）+ 转小写，用于宽松匹配。

    Excel 多行表头经常出现 "15.0kN(0.1Nd)位移读数" vs "15.0kN (0.1Nd) 位移读数" 这种细微差，
    肉眼一致但字符串不等。把空白全部抹掉再比就稳了。
    """
    return re.sub(r"[\s　]+", "", str(name)).lower()


def resolve_columns(
    template: dict[str, Any], available_cols: list[str]
) -> tuple[dict[str, str], list[str]]:
    """把模板里的所有 var_column / id_column 映射到 Excel 实际列名。

    返回 (resolved, missing)：
        resolved = {模板中的列名: Excel 实际列名}
        missing  = 模板需要但 Excel 里没有的列名列表
    支持精确匹配、空白容差匹配、大小写不敏感。
    """
    norm_to_actual: dict[str, str] = {_normalize_col(c): c for c in available_cols}

    needed: list[str] = [template["id_column"]]
    for curve in template.get("curves", []):
        for pt in curve.get("points", []):
            if pt.get("var_column") and pt["var_column"] not in needed:
                needed.append(pt["var_column"])

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for col in needed:
        if col in available_cols:
            resolved[col] = col
        else:
            actual = norm_to_actual.get(_normalize_col(col))
            if actual:
                resolved[col] = actual
            else:
                missing.append(col)
    return resolved, missing


def _series_from_template(
    curve_def: dict[str, Any],
    row: dict[str, Any],
    col_map: dict[str, str],
) -> CurveSeries | None:
    """把模板的曲线定义 + 一行 Excel 数据 → CurveSeries。

    col_map 把模板里的 var_column 映射到 Excel 实际列名（resolve_columns 产出）。
    fixed_axis='y' 表示 y 是给定常量、x 从 Excel 列读；'x' 反之。
    任何一个点缺数据则整条曲线返回 None。
    """
    xs: list[float] = []
    ys: list[float] = []
    for pt in curve_def["points"]:
        template_col = pt["var_column"]
        actual_col = col_map.get(template_col, template_col)
        if actual_col not in row:
            print(f"   ⚠️ 列 '{template_col}' 在 Excel 中找不到（已尝试空白容差匹配）")
            return None
        raw = row[actual_col]
        try:
            var_value = float(raw)
        except (TypeError, ValueError):
            print(f"   ⚠️ 列 '{actual_col}' 的值不是数字: {raw!r}")
            return None

        if pt["fixed_axis"] == "y":
            ys.append(float(pt["fixed_value"]))
            xs.append(var_value)
        elif pt["fixed_axis"] == "x":
            xs.append(float(pt["fixed_value"]))
            ys.append(var_value)
        else:
            raise ValueError(f"fixed_axis 必须是 'x' 或 'y'，得到 {pt['fixed_axis']!r}")

    return CurveSeries(
        name=curve_def["name"],
        xs=xs,
        ys=ys,
        color=curve_def.get("color", "#1F4FE0"),
        marker=curve_def.get("marker", "s"),
        linewidth=curve_def.get("linewidth", 2.0),
        markersize=curve_def.get("markersize", 7.0),
    )


def build_jobs(
    template: dict[str, Any], rows: list[dict[str, Any]], output_dir: str
) -> list[PlotJob]:
    """把模板 + 数据行 → 一组 PlotJob（每行一个）。

    会先解析列名映射；如果模板需要的列在 Excel 表头里完全找不到，整体返回空列表
    （上层调用方应该已经在预检阶段拦下了，这里再兜底一次）。
    """
    available_cols = list(rows[0].keys()) if rows else []
    col_map, missing = resolve_columns(template, available_cols)
    if missing:
        print("❌ 模板要求的列在 Excel 表头中找不到：")
        for m in missing:
            print(f"     - {m!r}")
        print("   Excel 实际表头：")
        for c in available_cols:
            print(f"     - {c!r}")
        print("   → 请用 [曲线模板编辑器] 修正列名后再运行。")
        return []

    id_col_actual = col_map[template["id_column"]]
    fname_tpl = template["filename_template"]
    title_tpl = template["title_template"]
    x_axis = _axis_spec_from_dict(template["x_axis"])
    y_axis = _axis_spec_from_dict(template["y_axis"])

    jobs: list[PlotJob] = []
    for idx, row in enumerate(rows, start=1):
        raw_id = row.get(id_col_actual)
        if raw_id is None or (isinstance(raw_id, float) and raw_id != raw_id):  # NaN
            print(f"⚠️ 第 {idx} 行标识列为空，跳过。")
            continue
        if isinstance(raw_id, float) and raw_id.is_integer():
            id_str = str(int(raw_id))
        else:
            id_str = str(raw_id).strip()

        series_list: list[CurveSeries] = []
        skip_row = False
        for curve_def in template["curves"]:
            s = _series_from_template(curve_def, row, col_map)
            if s is None:
                print(f"⚠️ 第 {idx} 行 ({template['id_column']}={id_str}) 数据不完整，跳过此行。")
                skip_row = True
                break
            series_list.append(s)
        if skip_row:
            continue

        jobs.append(
            PlotJob(
                title=title_tpl.format(id=id_str),
                output_path=os.path.join(output_dir, fname_tpl.format(id=id_str)),
                x_axis=x_axis,
                y_axis=y_axis,
                series=series_list,
            )
        )
    return jobs


def preflight_check(template: dict[str, Any], excel_columns: list[str]) -> tuple[bool, str]:
    """在跑批量前做体检：检查 Excel 表头是否覆盖模板需要的所有列。

    返回 (是否通过, 给用户看的诊断文本)。
    """
    col_map, missing = resolve_columns(template, excel_columns)
    needed = list(col_map.keys()) + missing
    n_total = len(needed)
    n_ok = len(col_map)

    lines: list[str] = []
    lines.append(
        f"📋 模板 '{template.get('id_column', '?')}' 共需 {n_total} 列；已匹配 {n_ok}，缺失 {len(missing)}。\n"
    )

    if col_map:
        lines.append("✅ 已匹配的列（左=模板，右=Excel 实际）:")
        for tpl_col, actual in col_map.items():
            tag = "  (容差)" if tpl_col != actual else ""
            lines.append(f"   • {tpl_col!r:50s} → {actual!r}{tag}")
        lines.append("")

    if missing:
        lines.append("❌ 模板需要但 Excel 找不到的列:")
        for m in missing:
            lines.append(f"   • {m!r}")
        lines.append("")
        lines.append("Excel 实际表头供参考:")
        for c in excel_columns:
            lines.append(f"   - {c!r}")
        lines.append("")
        lines.append("→ 请打开 [曲线模板编辑器] 把这些列名改成与 Excel 一致。")

    ok = len(missing) == 0
    return ok, "\n".join(lines)


def generate_example_excel(template: dict[str, Any], output_path: str, n_rows: int = 3) -> str:
    """根据模板生成一份示例 Excel —— 列名与模板完全一致，里面填几行假数据。

    给新人用：点一下就有标准格式的"模板答卷"，把自己的数据粘进去就能跑。
    """
    import pandas as pd

    # 收集模板需要的所有列：标识列 + 各曲线的 var_column
    cols: list[str] = [template["id_column"]]
    for curve in template.get("curves", []):
        for pt in curve.get("points", []):
            c = pt.get("var_column")
            if c and c not in cols:
                cols.append(c)

    # 假数据：标识列填 1..n_rows，其他列填一组合理的递增数字
    sample_rows = []
    for i in range(1, n_rows + 1):
        row: dict[str, Any] = {template["id_column"]: i}
        # 用每个 var_column 的 fixed_value 比例做一个示意值
        for j, col in enumerate(cols[1:], start=1):
            row[col] = round(0.3 * j + i * 0.05, 2)
        sample_rows.append(row)

    df = pd.DataFrame(sample_rows, columns=cols)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df.to_excel(output_path, index=False)
    return output_path


def read_rows(
    excel_path: str, sheet_name: str | None, header_row_index: int = 0
) -> list[dict[str, Any]]:
    """读 Excel 一个 Sheet，返回每行的字典（key=表头）。

    header_row_index=0 表示第 1 行是表头（pandas 的 0-based）。
    去掉表头列名两端空白。
    """
    import pandas as pd

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row_index)
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict(orient="records")


def run_plot_curves(
    excel_path: str,
    sheet_name: str | None,
    template_name: str,
    output_dir: str,
    templates_path: str = DEFAULT_TEMPLATES_PATH,
) -> list[str]:
    """工具入口：读 Excel → 套模板 → 批量出 PNG，返回写出的文件路径列表。"""
    print(f"📂 读取模板库: {templates_path}")
    templates = load_templates(templates_path)
    if template_name not in templates:
        raise KeyError(f"模板 '{template_name}' 不存在；可用：{get_template_names(templates)}")
    template = templates[template_name]
    print(f"   ↳ 选用模板: {template_name}")

    print(f"📊 读取 Excel: {excel_path}  Sheet: {sheet_name or '默认'}")
    rows = read_rows(excel_path, sheet_name)
    print(f"   ↳ 共 {len(rows)} 行数据")

    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 输出目录: {output_dir}")

    print("🔨 构建绘图任务...")
    jobs = build_jobs(template, rows, output_dir)
    print(f"   ↳ 有效任务 {len(jobs)} 个（已跳过空行/缺数据行）")

    written: list[str] = []
    for i, job in enumerate(jobs, start=1):
        try:
            render_plot(job)
            written.append(job.output_path)
            if i % 10 == 0 or i == len(jobs):
                print(f"   ↳ 进度 {i}/{len(jobs)}: {os.path.basename(job.output_path)}")
        except Exception as e:
            print(f"   ❌ 第 {i} 张失败: {os.path.basename(job.output_path)}: {e}")

    print(f"\n🎉 完成！共写出 {len(written)}/{len(jobs)} 张 PNG")
    return written


# ==========================================
# 模块 2：UI 流程
# ==========================================
def _request_params(
    excel_path: str, sheet_names: list[str], template_names: list[str]
) -> dict | None:
    default_dir = os.path.join(os.path.dirname(excel_path) or os.getcwd(), "曲线图")
    schema = [
        field_sheet_select(sheet_names),
        {
            "key": "template_name",
            "label": "曲线模板:",
            "type": "select",
            "options": template_names,
            "default": template_names[0] if template_names else "",
        },
        field_dir(default=default_dir),
    ]
    return ModernDynamicFormDialog(
        title="批量绘图 - 参数配置",
        form_schema=schema,
        width=620,
    ).show()


def _generate_example_flow(templates: dict[str, Any]) -> None:
    """走一遍"生成示例 Excel"的小流程：选模板 → 选输出位置 → 写文件。"""
    from tkinter import filedialog

    template_names = get_template_names(templates)

    schema = [
        {
            "key": "template_name",
            "label": "用哪个模板生成示例:",
            "type": "select",
            "options": template_names,
            "default": template_names[0],
        }
    ]
    params = ModernDynamicFormDialog(
        title="📋 生成示例 Excel - 选模板",
        form_schema=schema,
        width=520,
    ).show()
    if not params:
        return

    tpl_name = params.get("template_name") or template_names[0]
    template = templates[tpl_name]
    default_name = f"示例_{tpl_name}.xlsx"

    output_path = filedialog.asksaveasfilename(
        title="把示例 Excel 保存到哪里",
        defaultextension=".xlsx",
        initialfile=default_name,
        filetypes=[("Excel 文件", "*.xlsx")],
    )
    if not output_path:
        print("⚠️ 已取消：未选择输出位置。")
        return

    try:
        generate_example_excel(template, output_path)
    except Exception as e:
        ModernInfoDialog("生成失败", str(e)).show()
        return

    msg = (
        f"✅ 示例 Excel 已生成:\n{output_path}\n\n"
        f"列名与模板 '{tpl_name}' 完全对应；\n"
        f"把你自己的数据替换里面的示意值（一行 = 一张图），保存后再回来跑 [批量绘图] 即可。"
    )
    print(msg)
    ModernInfoDialog("示例已生成", msg).show()


def _main() -> None:
    enable_line_buffered_stdout()

    # === 入口选择：① 用现有数据画图  ② 先生成一份示例 Excel ===
    try:
        templates = load_templates()
    except Exception as e:
        ModernInfoDialog("加载模板失败", str(e)).show()
        return
    template_names = get_template_names(templates)
    if not template_names:
        ModernInfoDialog(
            "没有可用模板",
            f"请先打开 [曲线模板编辑器] 创建一个模板\n（也可手工编辑 {DEFAULT_TEMPLATES_PATH}）",
        ).show()
        return

    mode_dialog = ModernConfirmDialog(
        title="批量绘图 - 选择工作模式",
        message="想做什么？",
        sub_message=(
            "▶ 「确定执行」= 用我已有的 Excel 批量画图\n"
            "✖ 「取消」     = 我还不知道列名格式，先帮我生成一份示例 Excel"
        ),
    )
    if not mode_dialog.show():
        _generate_example_flow(templates)
        return

    excel_path = pick_excel_file(title="第一步：选择数据 Excel")
    if not excel_path:
        print("⚠️ 已取消：未选择 Excel 文件。")
        return

    sheets = read_sheet_names(excel_path)
    if not sheets:
        print("⚠️ 终止：该 Excel 没有可读取的工作表。")
        return

    params = _request_params(excel_path, sheets, template_names)
    if not params:
        print("⚠️ 已取消：未填参数。")
        return

    sheet_name = params.get("sheet_name") or sheets[0]
    template_name = params.get("template_name") or template_names[0]
    output_dir = params.get("output_dir") or os.path.join(os.path.dirname(excel_path), "曲线图")

    # === 预检阶段：先把 Excel 表头读出来跟模板对一遍，给用户看清楚再决定要不要跑 ===
    try:
        rows = read_rows(excel_path, sheet_name)
    except Exception as e:
        ModernInfoDialog("Excel 读取失败", str(e)).show()
        return

    if not rows:
        ModernInfoDialog("Sheet 为空", f"工作表 '{sheet_name}' 没有数据行。").show()
        return

    excel_cols = list(rows[0].keys())
    template = templates[template_name]
    ok, report = preflight_check(template, excel_cols)
    print("\n=== 预检报告 ===")
    print(report)

    if not ok:
        # 把缺失列单独抽出来，放在弹窗里直接给用户看
        col_map, missing = resolve_columns(template, excel_cols)
        miss_text = "\n".join(f"  • {m}" for m in missing[:8])
        if len(missing) > 8:
            miss_text += f"\n  …还有 {len(missing) - 8} 个"
        guide = (
            f"❌ 模板 '{template_name}' 里有 {len(missing)} 个列在你的 Excel 表头里找不到：\n\n"
            f"{miss_text}\n\n"
            f"=== 怎么修？三选一 ===\n\n"
            f"1️⃣ 推荐：回主控制台 → ⚙ 曲线模板 → 顶部「📂 挂载参考 Excel」选这个文件 →\n"
            f"   每个点的「列名」字段就变成下拉选项 → 选 Excel 里实际的列名 → 保存 → 再来一次\n\n"
            f"2️⃣ 反过来改 Excel 表头，让它跟模板列名一致（注意：含全/半角空格也要一致）\n\n"
            f"3️⃣ 如果只想要一份「答卷格式」参考：\n"
            f"   重新启动本工具 → 在第一个对话框点「取消」→ 选模板 → 生成示例 Excel"
        )
        print("\n" + guide)
        ModernInfoDialog("列名对不上 - 看这里有 3 种修法", guide).show()
        return

    if not ModernConfirmDialog(
        title="预检通过 - 是否继续",
        message=f"模板 '{template_name}' 的列与 Excel 表头全部对应。",
        sub_message=f"将处理 {len(rows)} 行数据，输出到:\n{output_dir}\n\n确认开始批量绘图？",
    ).show():
        print("⚠️ 用户取消。")
        return

    # === 真正跑批量 ===
    try:
        written = run_plot_curves(
            excel_path=excel_path,
            sheet_name=sheet_name,
            template_name=template_name,
            output_dir=output_dir,
        )
        ModernInfoDialog(
            "批量绘图完成",
            f"✅ 共写出 {len(written)} 张图\n\n输出目录:\n{output_dir}",
        ).show()
    except Exception as e:
        ModernInfoDialog("绘图异常", f"❌ 执行过程中出错:\n\n{e}").show()
        raise


if __name__ == "__main__":
    _main()
